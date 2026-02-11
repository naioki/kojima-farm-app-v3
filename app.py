"""
出荷ラベル生成Streamlitアプリ
FAX注文書画像をアップロードして、店舗ごとの出荷ラベルPDFを生成
"""
import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
from pdf_generator import LabelPDFGenerator
import tempfile
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict
import re
import traceback

# 設定管理モジュールのインポート
from config_manager import (
    load_stores, save_stores, add_store, remove_store,
    load_items, save_items, add_item_variant, add_new_item, remove_item,
    auto_learn_store, auto_learn_item,
    load_units, lookup_unit, add_unit_if_new, set_unit, initialize_default_units,
    load_item_settings, save_item_settings, get_item_setting, set_item_setting, set_item_receive_as_boxes, remove_item_setting,
    load_item_spec_master, save_item_spec_master,
    DEFAULT_ITEM_SETTINGS, get_box_count_items,
    get_effective_unit_size, get_min_shipping_unit, get_known_specs_for_item, is_spec_in_master, get_default_spec_for_item,
)
from email_config_manager import load_email_config, save_email_config, detect_imap_server, load_sender_rules, save_sender_rules
from email_reader import check_email_for_orders
from delivery_converter import v2_result_to_delivery_rows, v2_result_to_ledger_rows, ledger_rows_to_v2_format_with_units
from delivery_sheet_writer import append_delivery_rows, append_ledger_rows, fetch_ledger_rows, update_ledger_row_by_id, update_ledger_rows_unit_price_bulk, set_ledger_rows_confirmed, is_sheet_configured
from error_display_util import format_error_display
try:
    from delivery_sheet_writer import fetch_ledger_confirmed_dates
except ImportError:
    fetch_ledger_confirmed_dates = None
from order_processing import (
    safe_int,
    parse_order_image, parse_order_text, validate_and_fix_order_data,
    normalize_item_name, validate_store_name
)

# 台帳スプレッドシートのデフォルトID（Secretsに未設定の場合に使用）
DEFAULT_LEDGER_SPREADSHEET_ID = "1KJtpiaPjyH2bTaxULWwgemhZTCymfvsZPftfryQzXG4"

# ページ設定
st.set_page_config(
    page_title="出荷ラベル生成アプリ",
    page_icon="📦",
    layout="wide"
)

# セッション状態の初期化
if 'api_key' not in st.session_state:
    try:
        if hasattr(st, 'secrets'):
            try:
                st.session_state.api_key = st.secrets.get('GEMINI_API_KEY', '')
            except Exception:
                st.session_state.api_key = ''
        else:
            st.session_state.api_key = ''
    except Exception:
        st.session_state.api_key = ''
if 'parsed_data' not in st.session_state:
    st.session_state.parsed_data = None
if 'labels' not in st.session_state:
    st.session_state.labels = []
if 'shipment_date' not in st.session_state:
    st.session_state.shipment_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
if 'image_uploaded' not in st.session_state:
    st.session_state.image_uploaded = None
if 'email_config' not in st.session_state:
    try:
        secrets_obj = st.secrets if hasattr(st, 'secrets') else None
    except Exception:
        secrets_obj = None
    st.session_state.email_config = load_email_config(secrets_obj)
if 'email_password' not in st.session_state:
    st.session_state.email_password = ""

if 'default_units_initialized' not in st.session_state:
    initialize_default_units()
    item_settings = load_item_settings()
    for key in ["長ネギ", "長ねぎバラ", "長ネギバラ"]:
        if key in item_settings:
            if item_settings[key].get("default_unit") != 50 or item_settings[key].get("unit_type") != "本":
                set_item_setting(key, 50, "本")
    if not item_settings:
        save_item_settings(DEFAULT_ITEM_SETTINGS)
    st.session_state.default_units_initialized = True


def generate_labels_from_data(order_data: list, shipment_date: str) -> list:
    labels = []
    dt = datetime.strptime(shipment_date, '%Y-%m-%d')
    shipment_date_display = f"{dt.month}月{dt.day}日"
    for entry in order_data:
        store = entry.get('store', '')
        item = entry.get('item', '')
        spec = entry.get('spec', '')
        unit = safe_int(entry.get('unit', 0))
        boxes = safe_int(entry.get('boxes', 0))
        remainder = safe_int(entry.get('remainder', 0))
        if unit == 0:
            continue
        unit_label = get_unit_label_for_item(item, spec)
        total_boxes = boxes + (1 if remainder > 0 else 0)
        for i in range(boxes):
            labels.append({
                'store': store, 'item': item, 'spec': spec,
                'quantity': f"{unit}{unit_label}", 'sequence': f"{i+1}/{total_boxes}",
                'is_fraction': False, 'shipment_date': shipment_date_display,
                'unit': unit, 'boxes': boxes, 'remainder': remainder
            })
        if remainder > 0:
            labels.append({
                'store': store, 'item': item, 'spec': spec,
                'quantity': f"{remainder}{unit_label}", 'sequence': f"{total_boxes}/{total_boxes}",
                'is_fraction': True, 'shipment_date': shipment_date_display,
                'unit': unit, 'boxes': boxes, 'remainder': remainder
            })
    return labels


def get_unit_label_for_item(item: str, spec: str) -> str:
    setting = get_item_setting(item, spec)
    if setting.get("unit_type"):
        return setting["unit_type"]
    item_lower = item.lower() if item else ""
    spec_lower = spec.lower() if spec else ""
    unit_label = '本'
    if '長ねぎバラ' in item or '長ネギバラ' in item or 'ネギバラ' in item or 'ねぎバラ' in item or '長ねぎばら' in item:
        unit_label = '本'
    elif ('ネギ' in item or 'ねぎ' in item) and 'バラ' not in item and 'ばら' not in item:
        unit_label = '袋'
    elif '胡瓜バラ' in item or 'きゅうりバラ' in item or 'キュウリバラ' in item or '胡瓜ばら' in item:
        unit_label = '本'
    elif ('胡瓜' in item or 'きゅうり' in item) and 'バラ' not in item and 'ばら' not in item:
        unit_label = '袋'
    elif 'バラ' in spec or 'ばら' in spec_lower:
        if '胡瓜' in item or 'きゅうり' in item:
            unit_label = '本'
        elif 'ネギ' in item or 'ねぎ' in item:
            unit_label = '本'
    elif '春菊' in item or '青梗菜' in item or 'チンゲン菜' in item:
        unit_label = '袋'
    return unit_label


def generate_summary_table(order_data: list) -> list:
    summary = []
    for entry in order_data:
        store = entry.get('store', '')
        item = entry.get('item', '')
        spec = entry.get('spec', '')
        boxes = safe_int(entry.get('boxes', 0))
        remainder = safe_int(entry.get('remainder', 0))
        unit = safe_int(entry.get('unit', 0))
        rem_box = 1 if remainder > 0 else 0
        total_packs = boxes + rem_box
        total_quantity = (unit * boxes) + remainder
        unit_label = get_unit_label_for_item(item, spec)
        item_display = f"{item} {spec}".strip() if spec else item
        summary.append({
            'store': store, 'item': item, 'spec': spec, 'item_display': item_display,
            'boxes': boxes, 'rem_box': rem_box, 'total_packs': total_packs,
            'total_quantity': total_quantity, 'unit': unit, 'unit_label': unit_label
        })
    return summary


def generate_line_summary(order_data: list) -> str:
    summary_packs = defaultdict(int)
    for entry in order_data:
        unit = safe_int(entry.get('unit', 0))
        boxes = safe_int(entry.get('boxes', 0))
        remainder = safe_int(entry.get('remainder', 0))
        total = (unit * boxes) + remainder
        item = entry.get('item', '不明')
        spec = entry.get('spec', '').strip()
        key = (item, spec)
        summary_packs[key] += total
    line_text = f"【{datetime.now().strftime('%m/%d')} 出荷・作成総数】\n"
    sorted_items = sorted(summary_packs.items(), key=lambda x: (x[0][0], x[0][1]))
    for (item, spec), total in sorted_items:
        unit_label = get_unit_label_for_item(item, spec)
        display_name = f"{item} {spec}".strip() if spec else item
        line_text += f"・{display_name}：{total}{unit_label}\n"
    return line_text


NAV_FIELD = "現場用：出荷業務"
NAV_OFFICE = "事務用：請求管理"

with st.sidebar:
    st.header("⚙️ メニュー")
    nav_role = st.radio("業務", [NAV_FIELD, NAV_OFFICE], key="nav_role", label_visibility="collapsed")
    st.markdown("---")
    st.header("⚙️ 設定")
    try:
        if hasattr(st, 'secrets'):
            try:
                secrets_api_key = st.secrets.get('GEMINI_API_KEY', '')
                if secrets_api_key and not st.session_state.api_key:
                    st.session_state.api_key = secrets_api_key
                    st.info("✅ APIキーはSecretsから読み込まれました")
            except Exception:
                pass
    except Exception:
        pass
    api_key = st.text_input("Gemini APIキー", value=st.session_state.api_key, type="password")
    st.session_state.api_key = api_key
    st.markdown("---")
    st.subheader("📅 出荷日")
    shipment_date = st.date_input("出荷日を選択", value=datetime.strptime(st.session_state.shipment_date, '%Y-%m-%d').date())
    st.session_state.shipment_date = shipment_date.strftime('%Y-%m-%d')
    st.markdown("---")
    with st.expander("📋 使い方", expanded=False):
        st.markdown("1. APIキーを設定  \n2. 出荷日を選択  \n3. 画像をアップロード or メールから取得  \n4. 解析結果を確認・修正  \n5. PDFを生成")

# 事務用：請求管理（単価一括入力）— APIキー不要
if nav_role == NAV_OFFICE:
    st.title("📋 事務用：請求管理")
    st.caption("台帳データを行ごとに取得し、日付・納品先・品目・規格で絞り込んだうえで、単価や数量を一括で変更して反映できます。")
    try:
        secrets_obj_office = getattr(st, "secrets", None)
    except Exception:
        secrets_obj_office = None
    if not is_sheet_configured(secrets_obj_office):
        st.caption("💡 台帳を読むには .streamlit/secrets.toml に [gcp] を設定するか、GOOGLE_APPLICATION_CREDENTIALS を設定してください。")
        st.stop()
    _sid = ""
    try:
        if secrets_obj_office and hasattr(secrets_obj_office, "get"):
            _sid = secrets_obj_office.get("DELIVERY_SPREADSHEET_ID", "") or getattr(secrets_obj_office, "DELIVERY_SPREADSHEET_ID", "")
    except Exception:
        pass
    ledger_id_office = st.text_input("台帳のスプレッドシートID", value=_sid or DEFAULT_LEDGER_SPREADSHEET_ID, key="office_ledger_id")
    ledger_sheet_office = st.text_input("シート名", value="台帳データ", key="office_ledger_sheet")
    st.caption("取得する納品日付範囲（「日付範囲で行を取得」で使用。絞り込みにも使います）")
    office_col1, office_col2 = st.columns(2)
    with office_col1:
        office_date_from = st.date_input("納品日付（から）", value=datetime.now().date() - timedelta(days=30), key="office_date_from")
    with office_col2:
        office_date_to = st.date_input("納品日付（まで）", value=datetime.now().date(), key="office_date_to")
    office_fetch_col1, office_fetch_col2 = st.columns(2)
    with office_fetch_col1:
        if st.button("納品単価が0または空の行を取得", type="secondary", key="office_fetch_btn"):
            sid = (ledger_id_office or "").strip()
            if sid:
                ok, msg, rows = fetch_ledger_rows(sid, sheet_name=(ledger_sheet_office or "台帳データ").strip() or "台帳データ", only_unconfirmed=False, only_confirmed=False, only_zero_unit_price=True, st_secrets=secrets_obj_office)
                if ok:
                    st.session_state.office_zero_unit_rows = rows
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("スプレッドシートIDを入力してください。")
    with office_fetch_col2:
        if st.button("指定した日付範囲で行を取得", type="primary", key="office_fetch_by_date_btn"):
            sid = (ledger_id_office or "").strip()
            if sid:
                date_f_s = office_date_from.strftime("%Y/%m/%d")
                date_t_s = office_date_to.strftime("%Y/%m/%d")
                ok, msg, rows = fetch_ledger_rows(sid, sheet_name=(ledger_sheet_office or "台帳データ").strip() or "台帳データ", only_unconfirmed=False, only_confirmed=False, only_zero_unit_price=False, delivery_date_from=date_f_s, delivery_date_to=date_t_s, st_secrets=secrets_obj_office)
                if ok:
                    st.session_state.office_zero_unit_rows = rows
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("スプレッドシートIDを入力してください。")

    if st.session_state.get("office_zero_unit_rows"):
        rows_raw = st.session_state.office_zero_unit_rows
        stores_master = load_stores()
        spec_master = load_item_spec_master()
        items_master = sorted(set((r.get("品目") or "").strip() for r in spec_master if (r.get("品目") or "").strip()))
        stores_options = ["（すべて）"] + stores_master
        items_options = ["（すべて）"] + items_master

        # 品目名「胡瓜バラ」等は台帳では 品目=胡瓜・規格=バラ と分けて保存されていることがあるため、その組み合わせでもマッチさせる
        def _item_spec_for_composite(selected_item: str):
            if not selected_item or selected_item == "（すべて）":
                return None
            s = selected_item.strip()
            # 胡瓜: 胡瓜バラ→(胡瓜,バラ), 胡瓜平箱→(胡瓜,平箱)
            # 長ネギ: 長ねぎバラ/長ネギバラ→(長ネギ,バラ)。春菊・青梗菜は単品のみなので不要
            _map = {
                "胡瓜バラ": ("胡瓜", "バラ"),
                "胡瓜平箱": ("胡瓜", "平箱"),
                "長ねぎバラ": ("長ネギ", "バラ"),
                "長ネギバラ": ("長ネギ", "バラ"),
            }
            return _map.get(s)

        def _norm_d(s):
            if s is None or s == "": return ""
            return str(s).strip().replace("-", "/")

        st.subheader("絞り込み")
        st.caption("日付範囲は上で指定した「納品日付（から／まで）」で絞り込んでいます。変更する場合は上で日付を変えてください。")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.write("日付: " + office_date_from.strftime("%Y-%m-%d") + " ～ " + office_date_to.strftime("%Y-%m-%d"))
        with c2:
            filter_store = st.selectbox("納品先", options=stores_options, key="office_filter_store")
        with c3:
            filter_item = st.selectbox("品目", options=items_options, key="office_filter_item")

        date_from_s = _norm_d(office_date_from.strftime("%Y-%m-%d"))
        date_to_s = _norm_d(office_date_to.strftime("%Y-%m-%d"))
        # 日付・納品先・品目で絞った行から規格の選択肢を生成（データに存在する規格だけ表示）
        filtered_by_date_store_item = []
        composite = _item_spec_for_composite(filter_item)
        for r in rows_raw:
            d = _norm_d(r.get("納品日付", ""))
            if date_from_s and d < date_from_s:
                continue
            if date_to_s and d > date_to_s:
                continue
            store = (r.get("納品先") or "").strip()
            if filter_store and filter_store != "（すべて）" and store != filter_store:
                continue
            item = (r.get("品目") or "").strip()
            spec = (r.get("規格") or "").strip()
            if filter_item and filter_item != "（すべて）":
                if composite:
                    base_item, base_spec = composite
                    if not ((item == base_item and spec == base_spec) or item == filter_item):
                        continue
                elif item != filter_item:
                    continue
            filtered_by_date_store_item.append(r)
        specs_in_data = sorted(set((r.get("規格") or "").strip() for r in filtered_by_date_store_item))
        specs_options = ["（すべて）"] + [s if s else "（規格なし）" for s in specs_in_data]
        with c4:
            filter_spec = st.selectbox("規格", options=specs_options, key="office_filter_spec")

        filtered = []
        for r in filtered_by_date_store_item:
            spec = (r.get("規格") or "").strip()
            spec_display = spec if spec else "（規格なし）"
            if filter_spec and filter_spec != "（すべて）" and spec_display != filter_spec:
                continue
            filtered.append(r)

        if not filtered:
            st.info("条件に合う行がありません。")
            st.stop()

        # 選択列を追加（一括適用用）
        for i, r in enumerate(filtered):
            if "選択" not in r:
                r["選択"] = False
        df_office = pd.DataFrame(filtered)
        if "選択" not in df_office.columns:
            df_office["選択"] = False
        # 一括選択ボタンが押された場合は全行を選択状態にする（data_editorのキャッシュを消して反映させる）
        if st.session_state.get("office_select_all"):
            df_office["選択"] = True
            del st.session_state["office_select_all"]
            if "office_data_editor" in st.session_state:
                del st.session_state["office_data_editor"]

        sheet_display = (ledger_sheet_office or "台帳データ").strip() or "台帳データ"
        sid_display = (ledger_id_office or "").strip()
        sid_short = (sid_display[:12] + "…") if len(sid_display) > 12 else sid_display
        st.subheader("対象データ（編集・チェック後は下の一括適用を利用）")
        st.info(f"**適用先シート**: スプレッドシート ID `{sid_short}` の **「{sheet_display}」** に一括適用されます。（上で取得時に指定したID・シート名です）")
        if st.button("すべて選択", help="表示中の対象データをすべて選択します", key="office_select_all_btn"):
            st.session_state.office_select_all = True
            st.rerun()
        col_config_office = {}
        for col in df_office.columns:
            if col == "選択":
                col_config_office[col] = st.column_config.CheckboxColumn("選択", help="一括適用する行にチェック")
            elif col == "納品単価":
                col_config_office[col] = st.column_config.NumberColumn("納品単価", min_value=0, step=1)
            elif col == "納品金額":
                col_config_office[col] = st.column_config.NumberColumn("納品金額", min_value=0, step=1)
            elif col == "数量":
                col_config_office[col] = st.column_config.NumberColumn("数量", min_value=0, step=1)
            else:
                col_config_office[col] = st.column_config.TextColumn(col)
        edited_office_df = st.data_editor(df_office, width="stretch", hide_index=True, column_config=col_config_office, key="office_data_editor")

        st.subheader("一括更新")
        st.caption(f"適用先: シート「{sheet_display}」（スプレッドシート ID: {sid_short}）")
        apply_price = st.number_input("適用する単価", min_value=0, value=0, step=1, key="office_apply_price")
        if st.button("選択した行に一括適用", type="primary", key="office_apply_btn"):
            if apply_price <= 0:
                st.warning("適用する単価を1以上で入力してください。")
            else:
                selected_ids = []
                for idx, row in edited_office_df.iterrows():
                    ch = row.get("選択")
                    if ch is True or (isinstance(ch, str) and str(ch).strip().lower() in ("true", "1", "yes")):
                        did = row.get("納品ID")
                        if did:
                            selected_ids.append((str(did).strip(), row))
                if not selected_ids:
                    st.warning("一括適用する行にチェックを入れてください。")
                else:
                    sid = (ledger_id_office or "").strip()
                    sheet_s = (ledger_sheet_office or "台帳データ").strip() or "台帳データ"
                    updates_list = []
                    for did, row in selected_ids:
                        try:
                            qty = int(float(str(row.get("数量", 0)).replace(",", ""))) if row.get("数量") is not None else 0
                        except (ValueError, TypeError):
                            qty = 0
                        amount = apply_price * qty
                        updates_list.append({"納品ID": did, "納品単価": apply_price, "納品金額": amount})
                    ok, msg, ok_count = update_ledger_rows_unit_price_bulk(sid, sheet_s, updates_list, st_secrets=secrets_obj_office)
                    if ok and ok_count > 0:
                        st.success(f"✅ {ok_count}件を更新しました。（納品金額＝単価×数量で再計算）")
                        ok2, _, new_rows = fetch_ledger_rows(sid, sheet_name=sheet_s, only_unconfirmed=False, only_confirmed=False, only_zero_unit_price=True, st_secrets=secrets_obj_office)
                        if ok2:
                            st.session_state.office_zero_unit_rows = new_rows
                        st.rerun()
                    elif not ok:
                        st.error(msg)
    st.stop()

# 現場用：出荷業務
if not api_key:
    st.warning("⚠️ サイドバーでGemini APIキーを入力してください。")
    st.stop()

st.title("📦 出荷ラベル生成アプリ")
st.caption("画像アップロード・メール取得 → 解析・編集 → 納品データ・台帳連携・PDF生成まで一括で対応します。")
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📸 画像解析", "📧 メール自動読み取り", "📋 未確定一覧", "📄 台帳からPDF", "⚙️ 設定管理"])

with tab1:
    uploaded_file = st.file_uploader("注文画像をアップロード", type=['png', 'jpg', 'jpeg'])
    if uploaded_file:
        image = Image.open(uploaded_file)
        st.image(image, caption="アップロード画像", width="stretch")
        if st.session_state.image_uploaded != uploaded_file.name:
            st.session_state.parsed_data = None
            st.session_state.labels = []
            st.session_state.image_uploaded = uploaded_file.name
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔍 AI解析を実行", type="primary", use_container_width=True):
                with st.spinner('AIが解析中...'):
                    order_data = parse_order_image(image, api_key)
                    if order_data:
                        validated_data = validate_and_fix_order_data(order_data)
                        st.session_state.parsed_data = validated_data
                        st.session_state.labels = []
                        st.success(f"✅ {len(validated_data)}件のデータを読み取りました")
                        st.rerun()
                    else:
                        st.error("解析に失敗しました。")
        with col2:
            if st.button("🔄 解析結果をリセット", use_container_width=True):
                st.session_state.parsed_data = None
                st.session_state.labels = []
                st.rerun()

with tab2:
    st.subheader("📧 メール自動読み取り")
    st.write("メールから注文を自動取得して解析します。（画像・テキスト対応）")
    saved_config = st.session_state.email_config
    try:
        if hasattr(st, 'secrets'):
            try:
                secrets_email = st.secrets.get("email", {})
                if secrets_email and secrets_email.get("email_address"):
                    saved_config = {
                        "imap_server": secrets_email.get("imap_server", detect_imap_server(secrets_email.get("email_address", ""))),
                        "email_address": secrets_email.get("email_address", ""),
                        "sender_email": secrets_email.get("sender_email", ""),
                        "days_back": secrets_email.get("days_back", 1)
                    }
                    st.session_state.email_config = saved_config
                    st.info("💡 Streamlit Secretsから設定を読み込みました")
            except Exception:
                pass
    except Exception:
        pass
    with st.expander("📮 メール設定", expanded=False):
        default_imap = saved_config.get("imap_server", "") or (detect_imap_server(saved_config.get("email_address", "")) if saved_config.get("email_address") else "imap.gmail.com")
        imap_server = st.text_input("IMAPサーバー", value=default_imap or "imap.gmail.com")
        email_address = st.text_input("メールアドレス", value=saved_config.get("email_address", ""), key="email_addr_input")
        if email_address and "@" in email_address:
            auto_detected = detect_imap_server(email_address)
            if auto_detected != default_imap:
                imap_server = auto_detected
        email_password = st.text_input("パスワード", type="password", value=st.session_state.email_password, key="email_pass_input")
        st.session_state.email_password = email_password
        sender_email = st.text_input("送信者メール（フィルタ）", value=saved_config.get("sender_email", ""))
        days_back = st.number_input("何日前まで遡るか", min_value=1, max_value=30, value=saved_config.get("days_back", 1))
        save_settings = st.checkbox("設定を保存（パスワードは保存されません）", value=False)
        if save_settings:
            save_email_config(imap_server, email_address, sender_email, days_back, save_to_file=True)
            st.session_state.email_config = {"imap_server": imap_server, "email_address": email_address, "sender_email": sender_email, "days_back": days_back}
            st.success("✅ 設定を保存しました")
    col1, col2 = st.columns([2, 1])
    with col1:
        if st.button("📬 メールをチェック", type="primary", use_container_width=True):
            if not email_address or not email_password:
                st.error("メールアドレスとパスワードを入力してください。")
            else:
                try:
                    with st.spinner('メールをチェック中...'):
                        results = check_email_for_orders(imap_server=imap_server, email_address=email_address, password=email_password, sender_email=sender_email if sender_email else None, days_back=days_back)
                    
                    sender_rules = load_sender_rules()
                    
                    if results:
                        st.success(f"✅ {len(results)}件のデータを受信しました")
                        for idx, result in enumerate(results):
                            sender_addr = result['from']
                            rule = sender_rules.get(sender_addr, {}) # Exact match logic for now
                            # Try to match by email inside "Name <email>" if possible, but exact match is safer first.
                            # If key not found, try to extract email from "Name <email>" and check again?
                            # For simplicity, we use what 'from' returns (which might be "Name <email>").
                            # Ideally email_config_manager should handle fuzzy matching, but let's stick to exact or simple.
                            # Actually result['from'] is decoded subject which might be full string.
                            # Let's extract email address if possible.
                            
                            rule_mode = rule.get("mode", "image")
                            
                            subject_display = f"{result['subject']} ({result['date']})"
                            with st.expander(f"📎 {result['filename']} - {subject_display}"):
                                is_image = result.get('image') is not None
                                body_text = result.get('body_text', '')
                                
                                parse_type = "none"
                                if is_image:
                                    st.image(result['image'], caption=result['filename'], use_container_width=True)
                                    parse_type = "image"
                                elif body_text:
                                    st.text_area("メール本文", body_text, height=150)
                                    parse_type = "text"
                                
                                label = "🔍 解析を実行"
                                if parse_type == "image":
                                    label = "🔍 画像を解析"
                                elif parse_type == "text":
                                    label = "🔍 本文を解析"
                                
                                if parse_type != "none":
                                    if st.button(label, key=f"parse_{idx}_{parse_type}"):
                                        with st.spinner('解析中...'):
                                            parsed = None
                                            if parse_type == "image":
                                                parsed = parse_order_image(result['image'], api_key)
                                            else:
                                                parsed = parse_order_text(body_text, sender_addr, result['subject'], api_key)
                                            
                                            if parsed:
                                                validated_data = validate_and_fix_order_data(parsed)
                                                st.session_state.parsed_data = validated_data
                                                st.session_state.labels = []
                                                st.success(f"✅ {len(validated_data)}件のデータを読み取りました")
                                                st.rerun()
                    else:
                        st.info("新しいメールは見つかりませんでした。")
                except Exception as e:
                    st.error(format_error_display(e, "メールチェック"))
                    with st.expander("🔍 詳細"):
                        st.code(traceback.format_exc(), language="python")
    with col2:
        if st.button("🔄 設定をリセット", use_container_width=True):
            st.session_state.email_password = ""
            st.rerun()
    if saved_config.get("email_address"):
        st.success(f"💾 設定が保存されています: **{saved_config.get('email_address')}**")

with tab3:
    st.subheader("📋 未確定一覧")
    st.caption("台帳スプレッドシートから「確定フラグ」が空または「未確定」の行を表示します。取りこぼし・誤解析の確認に使えます。")
    try:
        secrets_obj = getattr(st, "secrets", None)
    except Exception:
        secrets_obj = None
    if is_sheet_configured(secrets_obj):
        _sid_ledger = ""
        try:
            if secrets_obj is not None and hasattr(secrets_obj, "get"):
                _sid_ledger = secrets_obj.get("DELIVERY_SPREADSHEET_ID", "") or getattr(secrets_obj, "DELIVERY_SPREADSHEET_ID", "")
        except Exception:
            pass
        ledger_id = st.text_input("台帳のスプレッドシートID", value=_sid_ledger or DEFAULT_LEDGER_SPREADSHEET_ID, placeholder="URLの /d/ と /edit の間の文字列", key="ledger_fetch_id")
        ledger_sheet_fetch = st.text_input("シート名", value="台帳データ", key="ledger_fetch_sheet")
        if st.button("未確定一覧を取得", key="fetch_unconfirmed_btn"):
            sid_stripped = (ledger_id or "").strip()
            if sid_stripped:
                ok, msg, rows = fetch_ledger_rows(sid_stripped, sheet_name=(ledger_sheet_fetch or "台帳データ").strip() or "台帳データ", only_unconfirmed=True, st_secrets=secrets_obj)
                if ok:
                    st.success(msg)
                    st.session_state.ledger_unconfirmed_rows = rows
                    st.session_state.ledger_fetch_timestamp = datetime.now() # Force refresh trigger
                else:
                    st.error(msg)
            else:
                st.warning("スプレッドシートIDを入力してください。")

        # 未確定行の表示と編集
        if st.session_state.get("ledger_unconfirmed_rows"):
            rows = st.session_state.ledger_unconfirmed_rows
            df_unconf = pd.DataFrame(rows)
            
            # 編集用設定
            edited_df = st.data_editor(
                df_unconf,
                width="stretch",
                hide_index=True,
                column_config={
                    "納品日付": st.column_config.TextColumn("納品日付", disabled=True),
                    "納品先": st.column_config.TextColumn("納品先", disabled=True),
                    "品目": st.column_config.TextColumn("品目", disabled=True),
                    "規格": st.column_config.TextColumn("規格", disabled=True),
                    "数量": st.column_config.NumberColumn("数量", min_value=0, step=1, required=True),
                    "農家": st.column_config.TextColumn("農家"),
                    "確定フラグ": st.column_config.SelectboxColumn("確定フラグ", options=["未確定", "確定"], required=True),
                    "確定日時": st.column_config.TextColumn("確定日時", disabled=True),
                    "チェック": st.column_config.CheckboxColumn("チェック", help="一括確定の対象にしたい行にチェック"),
                    "納品ID": st.column_config.TextColumn("納品ID", disabled=True),
                },
                key="ledger_editor"
            )

            # 一括確定
            sid_stripped = (ledger_id or "").strip()
            sheet_name_s = (ledger_sheet_fetch or "台帳データ").strip() or "台帳データ"
            if "confirm_bulk_all_ledger" not in st.session_state:
                st.session_state.confirm_bulk_all_ledger = False

            if st.session_state.confirm_bulk_all_ledger:
                n_all = len(rows)
                st.warning(f"**{n_all}件**を確定します。よろしいですか？")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("はい、確定する", type="primary", key="bulk_confirm_yes_btn"):
                        if sid_stripped:
                            all_ids = [str(r.get("納品ID", "")).strip() for r in rows if r.get("納品ID")]
                            ok, msg = set_ledger_rows_confirmed(sid_stripped, sheet_name_s, all_ids, st_secrets=secrets_obj)
                            st.session_state.confirm_bulk_all_ledger = False
                            if ok:
                                st.success(msg)
                                ok2, _, rows_new = fetch_ledger_rows(sid_stripped, sheet_name=sheet_name_s, only_unconfirmed=True, st_secrets=secrets_obj)
                                if ok2:
                                    st.session_state.ledger_unconfirmed_rows = rows_new
                                st.rerun()
                            else:
                                st.error(msg)
                        else:
                            st.error("スプレッドシートIDが設定されていません。")
                with col_no:
                    if st.button("キャンセル", key="bulk_confirm_no_btn"):
                        st.session_state.confirm_bulk_all_ledger = False
                        st.rerun()
            else:
                st.caption("**一括確定**: チェックした行だけ確定するか、表示中のすべてを確定できます。")
                col_check, col_all = st.columns(2)
                with col_check:
                    ids_checked = []
                    for _, row in edited_df.iterrows():
                        did = row.get("納品ID")
                        if not did:
                            continue
                        ch = row.get("チェック")
                        if ch is True or (isinstance(ch, str) and ch.strip().lower() in ("true", "1", "yes")) or ch == 1:
                            ids_checked.append(str(did).strip())
                    if st.button("✅ チェックした行を確定", key="bulk_confirm_checked_btn", disabled=len(ids_checked) == 0):
                        if sid_stripped and ids_checked:
                            ok, msg = set_ledger_rows_confirmed(sid_stripped, sheet_name_s, ids_checked, st_secrets=secrets_obj)
                            if ok:
                                st.success(msg)
                                ok2, _, rows_new = fetch_ledger_rows(sid_stripped, sheet_name=sheet_name_s, only_unconfirmed=True, st_secrets=secrets_obj)
                                if ok2:
                                    st.session_state.ledger_unconfirmed_rows = rows_new
                                st.rerun()
                            else:
                                st.error(msg)
                    elif len(ids_checked) == 0:
                        st.caption("チェックを入れた行がありません")
                with col_all:
                    if st.button("✅ 表示中のすべてを確定", key="bulk_confirm_all_btn"):
                        st.session_state.confirm_bulk_all_ledger = True
                        st.rerun()

            if st.button("💾 変更を保存 (スプレッドシートに反映)", type="primary", key="save_ledger_changes_btn"):
                sid_stripped = (ledger_id or "").strip()
                sheet_name_s = (ledger_sheet_fetch or "台帳データ").strip() or "台帳データ"
                
                if not sid_stripped:
                    st.error("スプレッドシートIDが設定されていません。")
                else:
                    updated_count = 0
                    errors = []
                    
                    # Original rows for comparison (keyed by delivery ID)
                    original_map = {r.get("納品ID"): r for r in rows}
                    
                    for index, row in edited_df.iterrows():
                        did = row.get("納品ID")
                        if not did:
                            continue
                        
                        orig = original_map.get(did)
                        if not orig:
                            continue
                        
                        updates = {}
                        # Check for changes in specific columns
                        # Quantity
                        try:
                            new_qty = int(row.get("数量", 0))
                            old_qty = int(orig.get("数量", 0)) if orig.get("数量") else 0
                            if new_qty != old_qty:
                                updates["数量"] = new_qty
                        except (ValueError, TypeError):
                            pass
                            
                        # Confirmed Flag
                        new_flag = row.get("確定フラグ")
                        old_flag = orig.get("確定フラグ")
                        if new_flag != old_flag:
                            updates["確定フラグ"] = new_flag
                            # Auto-set confirmed date if becoming confirmed
                            if new_flag == "確定":
                                updates["確定日時"] = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                        
                        # Farmer
                        new_farmer = row.get("農家")
                        old_farmer = orig.get("農家")
                        if new_farmer != old_farmer:
                            updates["農家"] = new_farmer

                        # Check
                        new_check = row.get("チェック") # Boolean or string depending on input
                        old_check = orig.get("チェック")
                        # Normalize check to boolean-like comparison if needed, or just string
                        if str(new_check) != str(old_check):
                            updates["チェック"] = new_check

                        if updates:
                            ok, msg = update_ledger_row_by_id(sid_stripped, sheet_name_s, did, updates, st_secrets=secrets_obj)
                            if ok:
                                updated_count += 1
                            else:
                                errors.append(f"ID {did}: {msg}")
                    
                    if updated_count > 0:
                        st.success(f"✅ {updated_count}件の行を更新しました。")
                        # Auto-refresh
                        ok, msg, rows = fetch_ledger_rows(sid_stripped, sheet_name=sheet_name_s, only_unconfirmed=True, st_secrets=secrets_obj)
                        if ok:
                            st.session_state.ledger_unconfirmed_rows = rows
                            st.rerun()
                    elif not errors:
                        st.info("変更された箇所はありませんでした。")
                    
                    if errors:
                        st.error(f"一部の更新に失敗しました:\n" + "\n".join(errors))

        st.caption("※ 納品IDが表示されていない行は更新できません。")
    else:
        st.caption("💡 台帳を読むには .streamlit/secrets.toml に [gcp] を設定するか、GOOGLE_APPLICATION_CREDENTIALS を設定してください。")

with tab4:
    st.subheader("📄 台帳からPDF")
    st.caption("台帳の「確定済み」データを納品日で取得し、差し札PDFを生成します。" + ("まず台帳から日付一覧を取得し、新しい順で選べます。" if fetch_ledger_confirmed_dates else "納品日付を選択して取得します。"))
    try:
        secrets_obj_pdf = getattr(st, "secrets", None)
    except Exception:
        secrets_obj_pdf = None
    if is_sheet_configured(secrets_obj_pdf):
        ledger_id_pdf = st.text_input("台帳のスプレッドシートID", value=DEFAULT_LEDGER_SPREADSHEET_ID, key="ledger_pdf_id")
        ledger_sheet_pdf = st.text_input("シート名", value="台帳データ", key="ledger_pdf_sheet")

        pdf_delivery_date = ""
        if fetch_ledger_confirmed_dates:
            # 台帳のデータから納品日付一覧を取得（新しい順）
            if "ledger_pdf_available_dates" not in st.session_state:
                st.session_state.ledger_pdf_available_dates = []
            if st.button("📅 台帳の日付一覧を取得（確定データから・新しい順）", type="primary", key="fetch_ledger_dates_btn"):
                sid = (ledger_id_pdf or "").strip()
                if sid:
                    ok, msg, dates = fetch_ledger_confirmed_dates(sid, sheet_name=(ledger_sheet_pdf or "台帳データ").strip() or "台帳データ", st_secrets=secrets_obj_pdf)
                    if ok:
                        st.session_state.ledger_pdf_available_dates = dates
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
                else:
                    st.warning("スプレッドシートIDを入力してください。")

            available_dates = st.session_state.ledger_pdf_available_dates
            if available_dates:
                selected = st.selectbox("納品日付を選択（データから取得・新しい順）", options=available_dates, key="pdf_ledger_date_select")
                pdf_delivery_date = (selected or "").replace("/", "-") if selected else ""
            else:
                st.info("👆 「台帳の日付一覧を取得」を押すと、確定済みの納品日が新しい順で表示されます。")
                default_date = datetime.now().date()
                try:
                    if st.session_state.get("shipment_date"):
                        default_date = datetime.strptime(st.session_state.get("shipment_date"), "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass
                pdf_date_input = st.date_input("納品日付（手動で指定する場合）", value=default_date, key="pdf_ledger_date_picker")
                pdf_delivery_date = pdf_date_input.strftime("%Y-%m-%d") if pdf_date_input else ""
        else:
            default_date = datetime.now().date()
            try:
                if st.session_state.get("shipment_date"):
                    default_date = datetime.strptime(st.session_state.get("shipment_date"), "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass
            pdf_date_input = st.date_input("納品日付（確定データの対象日）", value=default_date, key="pdf_ledger_date_picker")
            pdf_delivery_date = pdf_date_input.strftime("%Y-%m-%d") if pdf_date_input else ""

        if st.button("確定済みデータを取得", key="fetch_confirmed_btn"):
            sid = (ledger_id_pdf or "").strip()
            if sid and (pdf_delivery_date or "").strip():
                ok, msg, rows = fetch_ledger_rows(sid, sheet_name=(ledger_sheet_pdf or "台帳データ").strip() or "台帳データ", only_unconfirmed=False, only_confirmed=True, delivery_date_from=(pdf_delivery_date or "").strip(), delivery_date_to=(pdf_delivery_date or "").strip(), st_secrets=secrets_obj_pdf)
                if ok:
                    st.success(msg)
                    if rows:
                        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                        st.session_state.ledger_confirmed_for_pdf = rows
                    else:
                        st.info("該当する確定データがありません。")
                        st.session_state.ledger_confirmed_for_pdf = []
                else:
                    st.error(msg)
            else:
                st.warning("スプレッドシートIDと納品日付を入力してください。")
        if st.session_state.get("ledger_confirmed_for_pdf"):
            rows_for_pdf = st.session_state.ledger_confirmed_for_pdf
            def _get_unit(item, spec, store):
                u = lookup_unit(item, spec or "", store)
                if u and u > 0:
                    return u
                s = get_item_setting(item, spec)
                return s.get("default_unit", 1) or 1
            if st.button("PDFを生成（台帳の確定データから）", type="primary", key="pdf_from_ledger_btn"):
                v2_data = ledger_rows_to_v2_format_with_units(rows_for_pdf, get_unit_for_item=_get_unit)
                if v2_data:
                    try:
                        final_data = validate_and_fix_order_data(v2_data)
                        labels = generate_labels_from_data(final_data, pdf_delivery_date or st.session_state.shipment_date)
                        summary_data = generate_summary_table(final_data)
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                            pdf_path = tmp_file.name
                            generator = LabelPDFGenerator()
                            generator.generate_pdf(labels, summary_data, pdf_delivery_date or st.session_state.shipment_date, pdf_path)
                            with open(pdf_path, "rb") as f:
                                pdf_bytes = f.read()
                            safe_date_fn = (pdf_delivery_date or "").replace("/", "").replace("-", "")[:8]
                            st.download_button(label="📥 差し札PDFをダウンロード", data=pdf_bytes, file_name=f"出荷ラベル_台帳_{safe_date_fn}.pdf", mime="application/pdf", key="dl_pdf_ledger")
                            try:
                                os.unlink(pdf_path)
                            except (PermissionError, OSError):
                                pass
                        st.success("✅ PDFを生成しました。上のボタンからダウンロードしてください。")
                    except Exception as e:
                        st.error(format_error_display(e, "PDF生成"))
                        with st.expander("詳細"):
                            st.code(traceback.format_exc(), language="python")
                else:
                    st.warning("変換できるデータがありません。")
    else:
        st.caption("💡 台帳を読むには .streamlit/secrets.toml に [gcp] を設定してください。")

with tab5:
    st.subheader("⚙️ 設定管理")

    st.divider()
    st.subheader("📩 取引先メール解析設定")
    st.caption("送信者（メールアドレス）ごとに、画像解析するかテキスト解析するかを指定できます。")
    
    sender_rules = load_sender_rules()
    
    with st.expander("解析ルールを追加・編集", expanded=False):
        rule_sender = st.text_input("送信者メールアドレス", placeholder="example@farm.jp", key="rule_sender_input")
        rule_mode = st.selectbox("解析モード", ["image", "text", "both"], key="rule_mode_input", help="image: 画像のみ解析（デフォルト）\ntext: 本文のみ解析\nboth: 両方解析（未実装・将来用）")
        
        if st.button("ルールを保存", key="save_rule_btn"):
            if rule_sender and "@" in rule_sender:
                sender_rules[rule_sender.strip()] = {"mode": rule_mode}
                save_sender_rules(sender_rules)
                st.success(f"✅ {rule_sender} のルールを保存しました")
                st.rerun()
            else:
                st.warning("有効なメールアドレスを入力してください")
    
    if sender_rules:
        st.write("**登録済みルール:**")
        rules_to_delete = []
        for sender, rule in sender_rules.items():
            if not isinstance(rule, dict): continue
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"- **{sender}**: {rule.get('mode', 'image')}")
            with col2:
                if st.button("削除", key=f"del_rule_{sender}"):
                    del sender_rules[sender]
                    save_sender_rules(sender_rules)
                    st.rerun()
    st.divider()

    stores = load_stores()
    st.subheader("🏪 店舗名管理")
    col1, col2 = st.columns([3, 1])
    with col1:
        new_store = st.text_input("新しい店舗名を追加", placeholder="例: 新店舗", key="new_store_input")
    with col2:
        if st.button("追加", key="add_store"):
            if new_store and new_store.strip():
                if add_store(new_store.strip()):
                    st.success(f"✅ 「{new_store.strip()}」を追加しました")
                    st.rerun()
                else:
                    st.warning("既に存在する店舗名です")
    if stores:
        st.write("**登録済み店舗名:**")
        for store in stores:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"- {store}")
            with col2:
                if st.button("削除", key=f"del_store_{store}"):
                    if remove_store(store):
                        st.success(f"✅ 「{store}」を削除しました")
                        st.rerun()
    st.divider()
    st.subheader("🥬 品目名管理")
    items = load_items()
    item_settings = load_item_settings()
    box_count_items = get_box_count_items()
    spec_master = load_item_spec_master()
    if spec_master:
        master_rows = []
        for r in spec_master:
            u = r.get("default_unit", 0)
            t = r.get("unit_type", "袋")
            as_boxes = r.get("receive_as_boxes", False)
            spec = (r.get("規格") or "").strip()
            if not spec:
                spec = get_default_spec_for_item(r.get("品目", ""))
            master_rows.append({
                "品目": r.get("品目", ""),
                "規格": spec,
                "1コンテナあたりの入数": u,
                "単位": t,
                "受信方法": "箱数" if as_boxes else "総数",
            })
        if master_rows:
            df_master = pd.DataFrame(master_rows)
            edited_master = st.data_editor(df_master, width="stretch", hide_index=True,
                column_config={
                    "品目": st.column_config.TextColumn("品目"),
                    "規格": st.column_config.TextColumn("規格"),
                    "1コンテナあたりの入数": st.column_config.NumberColumn("1コンテナあたりの入数", min_value=1, step=1),
                    "単位": st.column_config.SelectboxColumn("単位", options=["袋", "本"], required=True),
                    "受信方法": st.column_config.SelectboxColumn("受信方法", options=["総数", "箱数"], required=True),
                })
            if st.button("💾 マスターデータを保存", key="save_master_btn", type="primary"):
                key_to_orig = {((r.get("品目") or "").strip(), (r.get("規格") or "").strip()): r for r in spec_master}
                out_rows = []
                for _, row in edited_master.iterrows():
                    name = str(row.get("品目", "")).strip()
                    spec = str(row.get("規格", "")).strip() if pd.notna(row.get("規格")) else ""
                    u = int(row["1コンテナあたりの入数"]) if row["1コンテナあたりの入数"] > 0 else 30
                    t = str(row["単位"]).strip() or "袋"
                    as_boxes = str(row["受信方法"]).strip() == "箱数"
                    orig = key_to_orig.get((name, spec)) or key_to_orig.get((name, ""))
                    min_ship = int(orig.get("min_shipping_unit", 0)) or 0 if orig else 0
                    out_rows.append({"品目": name, "規格": spec, "default_unit": u, "unit_type": t, "receive_as_boxes": as_boxes, "min_shipping_unit": min_ship})
                save_item_spec_master(out_rows)
                st.success("✅ マスターデータを保存しました。")
                st.rerun()
    st.divider()
    st.caption("新規追加: 品目と規格（任意）を入力して追加します。")
    new_item = st.text_input("品目名", placeholder="例: 胡瓜", key="new_item_input")
    new_spec = st.text_input("規格", placeholder="例: バラ・平箱（空欄可）", key="new_spec_input")
    row1 = st.columns(2)
    with row1[0]:
        new_item_unit = st.number_input("1コンテナあたりの入数", min_value=1, value=30, step=1, key="new_item_unit_input")
    with row1[1]:
        new_item_unit_type = st.selectbox("単位", ["袋", "本"], key="new_item_unit_type_input")
    if st.button("追加", key="add_item", type="primary"):
        if new_item and new_item.strip():
            item_name = new_item.strip()
            spec_name = (new_spec.strip() if new_spec and pd.notna(new_spec) else "")
            add_new_item(item_name)
            spec_master = load_item_spec_master()
            spec_master.append({
                "品目": item_name,
                "規格": spec_name,
                "default_unit": int(new_item_unit),
                "unit_type": new_item_unit_type,
                "receive_as_boxes": False,
            })
            save_item_spec_master(spec_master)
            st.session_state[f"item_expanded_{item_name}"] = True
            st.success(f"✅ 「{item_name}」" + (f"（規格: {spec_name}）" if spec_name else "") + " を追加しました")
            st.rerun()
        else:
            st.warning("品目名を入力してください")
    st.divider()
    if items:
        st.write("**登録済み品目名**")
        for normalized, variants in items.items():
            setting = get_item_setting(normalized)
            default_unit = setting.get("default_unit", 0)
            unit_type = setting.get("unit_type", "袋")
            receive_as_boxes = setting.get("receive_as_boxes", False)
            setting_info = f"入数: {default_unit}{unit_type}/コンテナ" if default_unit > 0 else "入数: 未設定"
            if receive_as_boxes:
                setting_info += "・箱数で受信"
            variants_display = ', '.join(variants[:3])
            if len(variants) > 3:
                variants_display += f" ... (+{len(variants)-3}件)"
            expander_title = f"📦 {normalized} ｜ {setting_info} ｜ バリアント: {variants_display}"
            with st.expander(expander_title, expanded=st.session_state.get(f"item_expanded_{normalized}", False)):
                new_variant = st.text_input(f"「{normalized}」の新しい表記を追加", key=f"variant_{normalized}", placeholder="例: 別表記")
                if st.button("追加", key=f"add_variant_{normalized}"):
                    if new_variant and new_variant.strip():
                        add_item_variant(normalized, new_variant.strip())
                        st.success(f"✅ 「{new_variant.strip()}」を追加しました")
                        st.rerun()
                st.divider()
                edit_unit = st.number_input("1コンテナあたりの入数", min_value=1, value=default_unit if default_unit > 0 else 30, step=1, key=f"edit_unit_{normalized}")
                edit_unit_type = st.selectbox("単位", ["袋", "本"], index=0 if unit_type == "袋" else 1, key=f"edit_unit_type_{normalized}")
                edit_receive = st.selectbox("受信方法", ["総数", "箱数"], index=1 if receive_as_boxes else 0, key=f"edit_receive_{normalized}")
                if st.button("保存", key=f"save_setting_{normalized}", use_container_width=True):
                    set_item_setting(normalized, int(edit_unit), edit_unit_type, receive_as_boxes=(edit_receive == "箱数"))
                    st.success(f"✅ 「{normalized}」の設定を保存しました")
                    st.rerun()
                st.divider()
                if st.button("🗑️ この品目を削除", key=f"del_item_{normalized}", type="secondary"):
                    if remove_item(normalized):
                        remove_item_setting(normalized)
                        st.success(f"✅ 「{normalized}」を削除しました")
                        st.rerun()

if st.session_state.parsed_data:
    st.markdown("---")
    st.header("📊 解析結果の確認・編集")
    st.write("以下のテーブルでデータを確認・編集できます。規格を変更すると入数・合計数量が再計算されます。編集後は「ラベルを生成」ボタンを押してください。")
    st.caption("品目・規格は一覧から選択できます（マスタ＋表の既存値）。入数は数値で直接入力できます。新しい品目は「設定管理」の品目名管理で追加してください。")
    df_data = []
    for entry in st.session_state.parsed_data:
        item_name = entry.get('item', '')
        normalized_item = normalize_item_name(item_name)
        spec_raw = entry.get('spec', '') or ''
        spec_s = str(spec_raw).strip() if spec_raw is not None else ''
        # 規格が空のときの自動入力: (1) 品目が胡瓜バラ/胡瓜平箱/長ねぎバラならバラ・平箱を補う (2) マスタに非空規格が1つだけならそれを使う
        if not spec_s and (normalized_item or item_name):
            item_key = (normalized_item or item_name).strip()
            composite_spec = {"胡瓜バラ": "バラ", "胡瓜平箱": "平箱", "長ねぎバラ": "バラ", "長ネギバラ": "バラ"}.get(item_key, "")
            if composite_spec:
                spec_s = composite_spec
                entry['spec'] = spec_s
            else:
                known = get_known_specs_for_item(normalized_item or item_name)
                non_empty = [s for s in known if s and str(s).strip()]
                if len(non_empty) == 1:
                    spec_s = str(non_empty[0]).strip()
                    entry['spec'] = spec_s
        unit = safe_int(entry.get('unit', 0))
        boxes = safe_int(entry.get('boxes', 0))
        remainder = safe_int(entry.get('remainder', 0))
        effective_unit = get_effective_unit_size(normalized_item or item_name, spec_s)
        # 「胡瓜バラ100×10」でAIが unit=10, boxes=0, remainder=0 の場合 → 入数100×単位数10=1000に補正
        if effective_unit > 0 and unit > 0 and unit < effective_unit and boxes == 0 and remainder == 0:
            unit = effective_unit
            boxes = safe_int(entry.get('unit', 0))
            remainder = 0
        # 「100×10」でAIが unit=100, boxes=0, remainder=10 の場合（10が単位数）→ 100×10=1000に補正
        elif effective_unit > 0 and unit == effective_unit and boxes == 0 and 0 < remainder < effective_unit:
            boxes = remainder
            remainder = 0
            entry['boxes'] = boxes
            entry['remainder'] = 0
        if unit == 0 and effective_unit > 0:
            unit = effective_unit
        total_quantity = (unit * boxes) + remainder
        df_data.append({'店舗名': entry.get('store', ''), '品目': entry.get('item', ''), '規格': spec_s, '入数(unit)': unit, '箱数(boxes)': boxes, '端数(remainder)': remainder, '合計数量': total_quantity})
    df = pd.DataFrame(df_data)
    # 品目・規格は選択＋既存値のハイブリッド用に選択肢を組み立て（マスタ＋現在の表の値）
    _items_dict = load_items()
    _item_names = set(_items_dict.keys()) | {v for variants in _items_dict.values() for v in (variants or [])}
    _spec_master = load_item_spec_master()
    _item_names |= {(r.get("品目") or "").strip() for r in _spec_master if (r.get("品目") or "").strip()}
    _spec_names = {(r.get("規格") or "").strip() for r in _spec_master}
    if not df.empty:
        _item_names |= set(df["品目"].dropna().astype(str).str.strip())
        _spec_names |= set(df["規格"].dropna().astype(str).str.strip())
    item_options = sorted(x for x in _item_names if x)
    spec_options = [""] + sorted(x for x in _spec_names if x)
    # 品目: 選択肢があればSelectbox（マスタ＋表の既存値）、なければ手入力のTextColumn
    col_品目 = st.column_config.SelectboxColumn("品目", options=item_options, required=True) if item_options else st.column_config.TextColumn("品目", required=True)
    col_規格 = st.column_config.SelectboxColumn("規格", options=spec_options) if spec_options else st.column_config.TextColumn("規格")
    edited_df = st.data_editor(df, width="stretch", num_rows="dynamic",
        column_config={
            "店舗名": st.column_config.SelectboxColumn("店舗名", options=load_stores(), required=True),
            "品目": col_品目,
            "規格": col_規格,
            "入数(unit)": st.column_config.NumberColumn("入数(unit)", min_value=0, step=1),
            "箱数(boxes)": st.column_config.NumberColumn("箱数(boxes)", min_value=0, step=1),
            "端数(remainder)": st.column_config.NumberColumn("端数(remainder)", min_value=0, step=1),
            "合計数量": st.column_config.NumberColumn("合計数量", disabled=True),
        })
    # 規格変更時: 入数をマスタ／規格名から再設定し、合計数量を再計算（num_rows=dynamic で追加行がある場合は idx>=len(df) で orig_row は None）
    for idx, row in edited_df.iterrows():
        spec_val = row.get('規格')
        if pd.isna(spec_val):
            spec_val = ''
        else:
            spec_val = str(spec_val).strip()
        orig_row = df.iloc[idx] if idx < len(df) else None
        orig_spec = ''
        if orig_row is not None:
            ospec = orig_row.get('規格')
            orig_spec = '' if pd.isna(ospec) else str(ospec).strip()
        if spec_val != orig_spec:
            eff = get_effective_unit_size(normalize_item_name(row.get('品目', '')) or row.get('品目', ''), spec_val)
            if eff > 0:
                edited_df.at[idx, '入数(unit)'] = eff
    u = edited_df['入数(unit)'].fillna(0)
    b = edited_df['箱数(boxes)'].fillna(0)
    r = edited_df['端数(remainder)'].fillna(0)
    edited_df['合計数量'] = (u * b + r).astype(int)
    df_for_compare = df.drop(columns=['合計数量'])
    edited_df_for_compare = edited_df.drop(columns=['合計数量'])
    if not df_for_compare.equals(edited_df_for_compare):
        updated_data = []
        for _, row in edited_df.iterrows():
            normalized_item = normalize_item_name(row.get('品目', '') or '')
            validated_store = validate_store_name(row.get('店舗名', '') or '') or (row.get('店舗名', '') or '')
            try:
                spec_value = row.get('規格')
                if pd.isna(spec_value) or spec_value is None:
                    spec_value = ''
                else:
                    spec_value = str(spec_value).strip()
            except (KeyError, TypeError):
                spec_value = ''
            unit_val = safe_int(row.get('入数(unit)', 0))
            boxes_val = safe_int(row.get('箱数(boxes)', 0))
            remainder_val = safe_int(row.get('端数(remainder)', 0))
            if unit_val > 0:
                set_unit(normalized_item or (row.get('品目') or ''), spec_value, validated_store, unit_val)
            updated_data.append({'store': validated_store, 'item': normalized_item, 'spec': spec_value, 'unit': unit_val, 'boxes': boxes_val, 'remainder': remainder_val})
        st.session_state.parsed_data = updated_data
        st.info("✅ データを更新しました。PDFを生成する場合は下のボタンを押してください。")
    # バリデーション: 最小出荷単位・規格マスタ不一致（品目が空の行はスキップ）
    validation_errors = []
    for idx, row in edited_df.iterrows():
        item = (row.get('品目') or '').strip()
        if not item:
            continue
        spec = row.get('規格')
        spec = '' if pd.isna(spec) else str(spec).strip()
        total_q = safe_int(row.get('合計数量', 0)) if pd.notna(row.get('合計数量')) else 0
        norm_item = normalize_item_name(item) or item
        min_q = get_min_shipping_unit(norm_item, spec)
        if min_q > 0 and total_q > 0 and total_q < min_q:
            validation_errors.append(f"行{idx+1}（{item} {spec or '規格なし'}）: 合計数量 {total_q} は最小出荷単位（{min_q}）を下回っています。")
        if not is_spec_in_master(norm_item, spec):
            known = get_known_specs_for_item(norm_item)
            if known:
                validation_errors.append(f"行{idx+1}（{item}）: 規格「{spec or '(空)'}」はマスタにありません。登録済み: {', '.join(s or '（規格なし）' for s in known)}。必要なら設定で追加するか、規格を修正してください。")
    if validation_errors:
        st.warning("⚠️ 以下の確認をお願いします：")
        for msg in validation_errors:
            st.markdown(f"- {msg}")
    st.divider()
    st.subheader("📋 納品データ形式（台帳用）")
    st.caption("持込入力と同一形式に変換してプレビュー・CSV出力・スプレッドシート追記ができます。")
    default_delivery = st.session_state.get("shipment_date", (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"))
    d_date = st.text_input("納品日付", value=default_delivery, key="delivery_date_input")
    c_date = st.text_input("持込日付", value=d_date, key="carry_date_input")
    farmer_name = st.text_input("農家", value="", placeholder="メール読み取りの場合は任意", key="farmer_input")
    delivery_rows = []
    parsed = st.session_state.parsed_data
    if isinstance(parsed, list) and parsed:
        try:
            delivery_rows = v2_result_to_delivery_rows(parsed, delivery_date=d_date or default_delivery, carry_date=(c_date or d_date or default_delivery), farmer=(farmer_name or "").strip())
        except Exception as e:
            st.warning(format_error_display(e, "変換"))
    if delivery_rows:
        df_delivery = pd.DataFrame(delivery_rows)
        st.dataframe(df_delivery, width="stretch", hide_index=True)
        csv_bytes = df_delivery.to_csv(index=False, encoding="utf-8-sig")
        safe_date = (d_date or "").replace("/", "-").replace("\\", "-").strip() or "export"
        st.download_button("📥 納品データをCSVでダウンロード", data=csv_bytes, file_name=f"納品データ_{safe_date}.csv", mime="text/csv", key="csv_delivery_btn")
        try:
            secrets_obj = getattr(st, "secrets", None)
        except Exception:
            secrets_obj = None
        if is_sheet_configured(secrets_obj):
            st.caption("台帳にデータを保存すると、ステータス「未確定」で台帳データシートに追記されます（二重管理なし・台帳一元化）。")
            _sid = ""
            try:
                if secrets_obj is not None and hasattr(secrets_obj, "get"):
                    _sid = secrets_obj.get("DELIVERY_SPREADSHEET_ID", "") or getattr(secrets_obj, "DELIVERY_SPREADSHEET_ID", "")
            except Exception:
                pass
            sheet_id = st.text_input("台帳のスプレッドシートID", value=_sid or DEFAULT_LEDGER_SPREADSHEET_ID, key="delivery_sheet_id")
            ledger_sheet_name = st.text_input("台帳シート名", value="台帳データ", key="ledger_sheet_name")
            if st.button("📤 台帳にデータを保存", type="primary", key="append_ledger_btn"):
                sid_stripped = (sheet_id or "").strip()
                if sid_stripped:
                    ledger_rows = v2_result_to_ledger_rows(parsed, delivery_date=d_date or default_delivery, farmer=(farmer_name or "").strip())
                    if ledger_rows:
                        ok, msg = append_ledger_rows(sid_stripped, ledger_rows, sheet_name=(ledger_sheet_name or "台帳データ").strip() or "台帳データ", st_secrets=secrets_obj)
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)
                    else:
                        st.warning("変換できる行がありません。")
                else:
                    st.warning("スプレッドシートIDを入力してください。")
        else:
            st.caption("💡 スプレッドシートへ追記するには .streamlit/secrets.toml に [gcp] を設定するか、GOOGLE_APPLICATION_CREDENTIALS を設定してください。")
    st.divider()
    if st.button("📋 ラベルを生成", type="primary", use_container_width=True, key="pdf_gen_tab1"):
        if st.session_state.parsed_data:
            try:
                final_data = validate_and_fix_order_data(st.session_state.parsed_data)
                labels = generate_labels_from_data(final_data, st.session_state.shipment_date)
                st.session_state.labels = labels
                if labels:
                    st.success(f"✅ {len(labels)}個のラベルを生成しました！")
                else:
                    st.error("❌ ラベルを生成できませんでした。")
            except Exception as e:
                st.error(format_error_display(e, "ラベル生成"))
                st.exception(e)

if st.session_state.labels and st.session_state.parsed_data:
    st.markdown("---")
    st.header("📄 PDF生成")
    if st.button("🖨️ PDFを生成", type="primary", use_container_width=True, key="pdf_gen_main"):
        try:
            final_data = validate_and_fix_order_data(st.session_state.parsed_data)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                pdf_path = tmp_file.name
                summary_data = generate_summary_table(final_data)
                generator = LabelPDFGenerator()
                generator.generate_pdf(st.session_state.labels, summary_data, st.session_state.shipment_date, pdf_path)
                with open(pdf_path, 'rb') as f:
                    pdf_bytes = f.read()
                st.download_button(label="📥 PDFをダウンロード (一覧表付き)", data=pdf_bytes, file_name=f"出荷ラベル_{st.session_state.shipment_date.replace('-', '')}.pdf", mime="application/pdf")
                try:
                    os.unlink(pdf_path)
                except (PermissionError, OSError):
                    pass
                st.success("✅ PDFが生成されました！")
            st.subheader("📋 LINE用集計（コピー用）")
            line_text = generate_line_summary(final_data)
            st.code(line_text, language="text")
        except Exception as e:
            st.error(format_error_display(e, "PDF生成"))
            with st.expander("🔍 詳細"):
                st.code(traceback.format_exc(), language="python")

st.markdown("---")
st.markdown("### 📝 注意事項")
st.markdown("- 店舗ごとにすべてのラベルが印刷されます（複数ページ対応）\n- 端数箱は太い破線枠で囲まれ、数量が大きく表示されます\n- 新しい店舗名・品目名は自動学習されます")
