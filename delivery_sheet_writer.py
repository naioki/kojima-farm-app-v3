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
# 台帳「台帳データ」用の列順（確定フラグ・確定日時・ステータス・単価含む）
LEDGER_SHEET_COLUMNS = [
    "納品日付", "納品先", "規格", "品目", "数量", "農家",
    "確定フラグ", "確定日時", "チェック", "納品ID",
    "納品単価", "納品金額", "ステータス",
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

def append_ledger_rows(
    spreadsheet_id: str,
    rows: List[Dict[str, Any]],
    sheet_name: str = "台帳データ",
    credentials=None,
    st_secrets=None,
) -> Tuple[bool, str]:
    """台帳シートに未確定行を追記（LEDGER_SHEET_COLUMNS の順で書き込み）"""
    if not rows or not isinstance(rows, list):
        return True, "追記する行がありません。"
    sid = (spreadsheet_id or "").strip()
    if not sid:
        return False, "スプレッドシートIDが指定されていません。"
    if not _validate_spreadsheet_id(sid):
        return False, "スプレッドシートIDの形式が正しくありません。"
    sheet_name_s = (sheet_name or "台帳データ").strip() or "台帳データ"
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
        import traceback
        traceback.print_exc()
        return False, f"スプレッドシートの取得に失敗しました: {repr(e)}"
    _defaults = {"ステータス": "未確定", "納品単価": 0, "納品金額": 0}
    data = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        data.append([_normalize_cell_value(row.get(col, _defaults.get(col, ""))) for col in LEDGER_SHEET_COLUMNS])
    if not data:
        return True, "追記する有効な行がありません。"
    try:
        for i in range(0, len(data), _APPEND_BATCH_SIZE):
            chunk = data[i : i + _APPEND_BATCH_SIZE]
            sheet.append_rows(chunk, value_input_option="USER_ENTERED")
    except Exception as e:
        return False, f"追記に失敗しました: {e}"
    return True, f"{len(data)} 行を台帳に追記しました（未確定）。"


def _is_zero_or_empty_unit_price(val: Any) -> bool:
    """納品単価が0または空とみなせるか"""
    if val is None or val == "":
        return True
    try:
        return float(str(val).strip().replace(",", "")) == 0
    except (ValueError, TypeError):
        return True


def fetch_ledger_rows(
    spreadsheet_id: str,
    sheet_name: str = "台帳データ",
    only_unconfirmed: bool = True,
    only_confirmed: bool = False,
    only_zero_unit_price: bool = False,
    delivery_date_from: Optional[str] = None,
    delivery_date_to: Optional[str] = None,
    credentials=None,
    st_secrets=None,
) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    台帳シートから行を取得。
    - only_unconfirmed=True: 確定フラグが空または「未確定」の行のみ。
    - only_confirmed=True: 確定フラグが「確定」の行のみ（PDF用）。
    - only_zero_unit_price=True: 納品単価（I列想定）が0または空の行のみ（事務・単価一括入力用）。
    - delivery_date_from / _to: 納品日付でフィルタ（YYYY/MM/DD または YYYY-MM-DD 形式）。
    Returns: (成功可否, メッセージ, 行のリスト)
    """
    sid = (spreadsheet_id or "").strip()
    if not sid:
        return False, "スプレッドシートIDが指定されていません。", []
    if not _validate_spreadsheet_id(sid):
        return False, "スプレッドシートIDの形式が正しくありません。", []
    sheet_name_s = (sheet_name or "台帳データ").strip() or "台帳データ"
    creds = credentials or _get_credentials(st_secrets)
    if creds is None:
        return False, "Google スプレッドシート用の認証が設定されていません。", []
    try:
        import gspread
    except ImportError:
        return False, "gspread がインストールされていません。", []
    try:
        client = gspread.authorize(creds)
        workbook = client.open_by_key(sid)
        sheet = workbook.worksheet(sheet_name_s)
        all_values = sheet.get_all_values()
    except Exception as e:
        return False, f"スプレッドシートの取得に失敗しました: {str(e).strip() or '不明なエラー'}", []
    if not all_values or len(all_values) < 2:
        return True, "データがありません。", []
    header = [str(h).strip() for h in all_values[0]]
    idx_confirmed = None
    idx_delivery_date = None
    has_status_col = "ステータス" in header
    for i, h in enumerate(header):
        if h == "確定フラグ":
            idx_confirmed = i
        if h == "納品日付":
            idx_delivery_date = i
    def _norm_d(s: str) -> str:
        if not s:
            return ""
        return str(s).strip().replace("-", "/")

    rows_out: List[Dict[str, Any]] = []
    for r in all_values[1:]:
        while len(r) < len(header):
            r.append("")
        row_dict = {header[i]: r[i] for i in range(len(header))}
        status_val = (row_dict.get("ステータス") or "").strip()
        if only_unconfirmed and not only_zero_unit_price:
            if has_status_col:
                if status_val and status_val not in ("", "未確定"):
                    continue
            elif idx_confirmed is not None:
                val = (row_dict.get("確定フラグ") or "").strip()
                if val and val != "未確定":
                    continue
        if only_confirmed:
            if has_status_col:
                if status_val not in ("確定", "請求済"):
                    continue
            elif idx_confirmed is not None:
                val = (row_dict.get("確定フラグ") or "").strip()
                if val != "確定":
                    continue
        if delivery_date_from is not None or delivery_date_to is not None:
            if idx_delivery_date is None:
                continue
            d = _norm_d(row_dict.get("納品日付", ""))
            if delivery_date_from and _norm_d(delivery_date_from) > d:
                continue
            if delivery_date_to and d > _norm_d(delivery_date_to):
                continue
        if only_zero_unit_price:
            unit_price_val = row_dict.get("納品単価", "")
            if not _is_zero_or_empty_unit_price(unit_price_val):
                continue
            if has_status_col and status_val not in ("", "未確定"):
                continue
        rows_out.append(row_dict)
    msg = f"{len(rows_out)} 件を取得しました。"
    if only_unconfirmed:
        msg = f"{len(rows_out)} 件の未確定行を取得しました。"
    elif only_confirmed:
        msg = f"{len(rows_out)} 件の確定行を取得しました。"
    return True, msg, rows_out


def fetch_ledger_confirmed_dates(
    spreadsheet_id: str,
    sheet_name: str = "台帳データ",
    credentials=None,
    st_secrets=None,
) -> Tuple[bool, str, List[str]]:
    """
    台帳シートの「確定」行から、納品日付の一覧を重複なしで取得する。
    返す日付は YYYY/MM/DD 形式で、新しい順（降順）にソート済み。
    Returns: (成功可否, メッセージ, 日付文字列のリスト)
    """
    ok, msg, rows = fetch_ledger_rows(
        spreadsheet_id,
        sheet_name=sheet_name,
        only_unconfirmed=False,
        only_confirmed=True,
        delivery_date_from=None,
        delivery_date_to=None,
        credentials=credentials,
        st_secrets=st_secrets,
    )
    if not ok or not rows:
        return ok, msg, []
    seen: set = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = (row.get("納品日付") or "").strip().replace("-", "/")
        if d:
            seen.add(d)
    out = sorted(seen, reverse=True)
    return True, f"確定データの納品日付 {len(out)} 件（新しい順）", out


def update_ledger_row_by_id(
    spreadsheet_id: str,
    sheet_name: str,
    delivery_id: str,
    updates: Dict[str, Any],
    credentials=None,
    st_secrets=None,
) -> Tuple[bool, str]:
    """
    台帳シートで納品IDが一致する行を探し、指定した列だけ上書きする。
    updates のキーは LEDGER_SHEET_COLUMNS の列名（例: "数量", "確定フラグ", "確定日時"）。
    """
    sid = (spreadsheet_id or "").strip()
    if not sid or not _validate_spreadsheet_id(sid):
        return False, "スプレッドシートIDが不正です。"
    sheet_name_s = (sheet_name or "台帳データ").strip() or "台帳データ"
    delivery_id_s = (delivery_id or "").strip()
    if not delivery_id_s:
        return False, "納品IDを指定してください。"
    if not updates or not isinstance(updates, dict):
        return True, "更新する項目がありません。"
    creds = credentials or _get_credentials(st_secrets)
    if creds is None:
        return False, "Google スプレッドシート用の認証が設定されていません。"
    try:
        import gspread
    except ImportError:
        return False, "gspread がインストールされていません。"
    try:
        client = gspread.authorize(creds)
        workbook = client.open_by_key(sid)
        sheet = workbook.worksheet(sheet_name_s)
        all_values = sheet.get_all_values()
    except Exception as e:
        return False, f"スプレッドシートの取得に失敗しました: {str(e)}"
    if not all_values or len(all_values) < 2:
        return False, "データがありません。"
    header = [str(h).strip() for h in all_values[0]]
    col_name_to_idx = {h: i for i, h in enumerate(header)}
    id_col = "納品ID"
    if id_col not in col_name_to_idx:
        return False, "台帳に「納品ID」列がありません。"
    id_idx = col_name_to_idx[id_col]
    row_found = None  # 1-based row index for update_cell
    for r in range(1, len(all_values)):
        row = all_values[r]
        if id_idx < len(row) and str(row[id_idx]).strip() == delivery_id_s:
            row_found = r + 1  # gspread is 1-based
            break
    if row_found is None:
        return False, f"納品ID「{delivery_id_s}」の行が見つかりません。"
    # 数量を更新する場合は納品金額を再計算（納品金額＝納品単価×数量）
    if "数量" in updates:
        row_data = all_values[row_found - 1]
        unit_price = 0.0
        try:
            if "納品単価" in col_name_to_idx:
                idx = col_name_to_idx["納品単価"]
                if idx < len(row_data):
                    unit_price = float(str(row_data[idx]).replace(",", "").strip() or 0)
        except (ValueError, TypeError):
            pass
        try:
            qty = int(float(str(updates["数量"]).replace(",", ""))) if updates.get("数量") is not None else 0
        except (ValueError, TypeError):
            qty = 0
        qty = max(0, qty)  # 負数は0扱い
        amount = max(0, int(round(unit_price * qty)))
        updates = dict(updates)
        if "納品金額" in col_name_to_idx:
            updates["納品金額"] = amount
    for col_name, value in updates.items():
        if col_name not in col_name_to_idx:
            continue
        col_idx = col_name_to_idx[col_name] + 1  # 1-based
        try:
            sheet.update_cell(row_found, col_idx, _normalize_cell_value(value))
        except Exception as e:
            return False, f"更新に失敗しました（{col_name}）: {e}"
    return True, "1行を更新しました。"


def set_ledger_rows_confirmed(
    spreadsheet_id: str,
    sheet_name: str,
    delivery_ids: List[str],
    credentials=None,
    st_secrets=None,
) -> Tuple[bool, str]:
    """
    指定した納品IDの行を一括で「確定」にする（確定フラグ＝確定、確定日時＝現在時刻）。
    シートを1回だけ読み、update_cells で一括書き込みするため 429（Read クォータ超過）を防ぐ。
    """
    if not delivery_ids or not isinstance(delivery_ids, list):
        return True, "対象がありません。"
    ids_set = {str(did).strip() for did in delivery_ids if did and str(did).strip()}
    if not ids_set:
        return True, "対象がありません。"
    from datetime import datetime
    confirmed_at = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    creds = credentials or _get_credentials(st_secrets)
    if creds is None:
        return False, "Google スプレッドシート用の認証が設定されていません。"
    try:
        import gspread
        try:
            from gspread.cell import Cell
        except ImportError:
            from gspread.models import Cell  # gspread 5.x
    except ImportError:
        return False, "gspread がインストールされていません。"
    sid = (spreadsheet_id or "").strip()
    if not sid or not _validate_spreadsheet_id(sid):
        return False, "スプレッドシートIDが不正です。"
    sheet_name_s = (sheet_name or "台帳データ").strip() or "台帳データ"
    try:
        client = gspread.authorize(creds)
        workbook = client.open_by_key(sid)
        sheet = workbook.worksheet(sheet_name_s)
        all_values = sheet.get_all_values()
    except Exception as e:
        return False, f"スプレッドシートの取得に失敗しました: {str(e)}"
    if not all_values or len(all_values) < 2:
        return False, "データがありません。"
    header = [str(h).strip() for h in all_values[0]]
    col_name_to_idx = {h: i for i, h in enumerate(header)}
    if "納品ID" not in col_name_to_idx or "確定フラグ" not in col_name_to_idx or "確定日時" not in col_name_to_idx:
        return False, "台帳に「納品ID」「確定フラグ」「確定日時」列が必要です。"
    id_idx = col_name_to_idx["納品ID"]
    col_flag = col_name_to_idx["確定フラグ"] + 1  # 1-based
    col_date = col_name_to_idx["確定日時"] + 1
    id_to_row: Dict[str, int] = {}
    for r in range(1, len(all_values)):
        row = all_values[r]
        if id_idx < len(row):
            did = str(row[id_idx]).strip()
            if did in ids_set:
                id_to_row[did] = r + 1  # 1-based
    if not id_to_row:
        return False, "指定した納品IDの行が見つかりません。"
    cells: List[Cell] = []
    for did in ids_set:
        row_1 = id_to_row.get(did)
        if not row_1:
            continue
        cells.append(Cell(row=row_1, col=col_flag, value="確定"))
        cells.append(Cell(row=row_1, col=col_date, value=confirmed_at))
    try:
        sheet.update_cells(cells)
    except Exception as e:
        return False, f"一括更新に失敗しました: {str(e)}"
    return True, f"{len(id_to_row)}件を確定しました。"


def is_sheet_configured(st_secrets=None) -> bool:
    return _get_credentials(st_secrets) is not None
