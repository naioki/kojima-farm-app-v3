"""
注文データ処理モジュール
画像/テキスト解析、データ検証、正規化ロジックを担当
"""
import json
import re
import google.generativeai as genai
import streamlit as st # UIフィードバック用に一時的に維持
from PIL import Image
from typing import List, Dict, Optional, Any

from config_manager import (
    load_stores, auto_learn_store,
    load_items, auto_learn_item,
    load_item_settings, get_box_count_items,
    lookup_unit, get_item_setting, add_unit_if_new,
    get_effective_unit_size,
    load_item_spec_master,
    get_default_spec_for_item,
)
from error_display_util import format_error_display

def safe_int(v):
    if v is None:
        return 0
    if isinstance(v, int):
        return v
    s = re.sub(r'\D', '', str(v))
    return int(s) if s else 0

def get_known_stores():
    return load_stores()

def get_item_normalization():
    return load_items()


def _compute_boxes_remainder_from_total(entries: list) -> None:
    """
    AIが返した合計数量(total)から、Pythonで箱数・端数を計算して entry に設定する。
    箱数 = 合計数量 ÷ 入数 の商、端数 = 余り。入数は入り数マスタ（品目名管理）を常に優先する。
    """
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        total = safe_int(entry.get("total", 0))
        if "total" not in entry:
            continue
        item = (entry.get("item") or "").strip()
        spec = (entry.get("spec") or "").strip()
        normalized = normalize_item_name(item, auto_learn=False)
        setting = get_item_setting(normalized or item, spec)
        unit = int(setting.get("default_unit", 0)) or 0
        if unit <= 0:
            unit = safe_int(entry.get("unit", 0))
        if unit <= 0:
            entry["boxes"] = 0
            entry["remainder"] = total
        else:
            entry["unit"] = unit
            entry["boxes"] = total // unit
            entry["remainder"] = total % unit


def _fix_boxes_remainder_when_count_misread_as_boxes(entries: list) -> None:
    """
    平箱以外の品目で、AIが個数（総数）を箱数に入れてしまった場合に補正する。
    例：春菊×20 → 正しくは boxes=0, remainder=20。AIが boxes=20, remainder=0 と出したら直す。
    条件: receive_as_boxes でない かつ remainder=0 かつ 0 < boxes <= unit → boxes を総数と解釈し直す。
    """
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item = (entry.get("item") or "").strip()
        spec = (entry.get("spec") or "").strip()
        unit = safe_int(entry.get("unit", 0))
        boxes = safe_int(entry.get("boxes", 0))
        remainder = safe_int(entry.get("remainder", 0))
        if unit <= 0 or remainder != 0 or boxes <= 0:
            continue
        normalized_item = normalize_item_name(item, auto_learn=False)
        setting = get_item_setting(normalized_item or item, spec)
        if setting.get("receive_as_boxes", False):
            continue
        if boxes <= unit:
            total = boxes
            entry["boxes"] = total // unit
            entry["remainder"] = total % unit


def normalize_spec_from_parse(spec_str: str) -> str:
    """
    メール・画像解析で得た規格を、品目名管理マスタに合わせて正規化する。
    - ばら / バラ → バラ
    - 平箱 → 平箱
    - N本（数字+本）→ そのまま（3本, 2本, 50本など）
    - 上記以外は前後空白を取って返す
    """
    if spec_str is None:
        return ""
    s = str(spec_str).strip()
    if not s:
        return ""
    # ひらがな「ばら」→「バラ」
    if s in ("ばら", "バラ"):
        return "バラ"
    if s == "平箱":
        return "平箱"
    # 数字+本（2本, 3本, 50本など）はそのまま
    if re.match(r"^\d+本$", s):
        return s
    return s


def _build_spec_master_prompt_sections():
    """
    品目名管理（品目+規格マスタ）から、Geminiプロンプト用の文字列を組み立てる。
    返す値: (unit_lines, box_count_str, spec_master_section)
    - unit_lines: 「品目(規格): 入数単位/コンテナ」のリスト（計算ルール用）
    - box_count_str: 箱数で受信する品目・規格の一覧（「×数字」が箱数の品目）
    - spec_master_section: プロンプト用の【品目・規格マスタ】ブロック全文
    """
    spec_master = load_item_spec_master()
    unit_parts = []
    box_items = []
    table_lines = []
    for r in spec_master:
        item = (r.get("品目") or "").strip()
        spec = (r.get("規格") or "").strip()
        spec_display = spec if spec else "規格なし"
        u = int(r.get("default_unit", 0)) or 0
        t = (r.get("unit_type") or "袋").strip() or "袋"
        as_boxes = bool(r.get("receive_as_boxes", False))
        if not item:
            continue
        label = f"{item}({spec_display})" if spec else item
        if u > 0:
            unit_parts.append(f"- {label}: {u}{t}/コンテナ")
        table_lines.append(f"- {label}: {u}{t}/コンテナ, 受信方法={'箱数' if as_boxes else '総数'}")
        if as_boxes:
            box_items.append(label)
    unit_lines = "\n".join(unit_parts) if unit_parts else "（品目名管理で入数を登録してください）"
    box_count_str = "、".join(box_items) if box_items else "（なし）"
    spec_master_section = "【品目・規格マスタ（読み取り・計算の参照）】\n" + "\n".join(table_lines) if table_lines else ""
    return unit_lines, box_count_str, spec_master_section


def normalize_item_name(item_name, auto_learn=True):
    if not item_name:
        return ""
    item_name = str(item_name).strip()
    item_normalization = get_item_normalization()
    for normalized, variants in item_normalization.items():
        if item_name in variants or any(variant in item_name for variant in variants):
            return normalized
    if auto_learn:
        return auto_learn_item(item_name)
    return item_name

def validate_store_name(store_name, auto_learn=True):
    if not store_name:
        return None
    store_name = str(store_name).strip()
    known_stores = get_known_stores()
    if store_name in known_stores:
        return store_name
    for known_store in known_stores:
        if known_store in store_name or store_name in known_store:
            return known_store
    if auto_learn:
        return auto_learn_store(store_name)
    return None

def parse_order_image(image: Image.Image, api_key: str) -> list:
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception:
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
        except Exception:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
            except Exception:
                try:
                    model = genai.GenerativeModel('gemini-1.5-pro')
                except Exception:
                    model = genai.GenerativeModel('gemini-pro-vision')
    known_stores = get_known_stores()
    item_normalization = get_item_normalization()
    store_list = "、".join(known_stores)
    unit_lines, box_count_str, spec_master_section = _build_spec_master_prompt_sections()
    prompt = f"""
    画像を解析し、以下の厳密なルールに従ってJSONで返してください。
    
    【店舗名リスト（参考）】
    {store_list}
    ※上記リストにない店舗名も読み取ってください。
    
    【品目名の正規化ルール】
    {json.dumps(item_normalization, ensure_ascii=False, indent=2)}
    
    {spec_master_section}
    
    【重要ルール】
    1. 店舗名の後に「:」または改行がある場合、その後の行は全てその店舗の注文です
    2. 品目名がない行（例：「50×1」）は、直前の品目の続きとして処理してください
    3. 「/」で区切られた複数の注文は、同じ店舗・同じ品目として統合してください
    4. 「胡瓜バラ」と「胡瓜3本」は別の規格として扱ってください
    5. unit と total には「数字のみ」を入れてください。箱数・端数は出力不要です（Python側で計算します）。
    
    【計算ルール（上記マスタ＝1コンテナあたりの入数）】
    {unit_lines}
    
    【合計数量(total)の取り方】
    - 合計数量：メール内の「×」の後の数字を合計数量(total)とします。※「胡瓜バラ 50×4」のように「数×数」の表記の場合は、50×4＝200 として total に入れてください。
    - 箱数で受信する品目（{box_count_str}）のみ：「×」の後の数字を箱数とし、合計数量＝箱数×入数 として total に入れてください（例：4箱・入数30 → total=120）。
    
    【出力JSON形式】
    [{{"store":"店舗名","item":"品目名","spec":"規格","unit":数字,"total":数字}}]
    
    （画像からの解析ですが、形式は同じJSONです）
    
    必ず全ての店舗と品目を漏れなく読み取ってください。
    """
    try:
        response = model.generate_content([prompt, image])
        text = response.text.strip()
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            parts = text.split('```')
            for part in parts:
                if '{' in part and '[' in part:
                    text = part.strip()
                    break
        result = json.loads(text)
        if isinstance(result, dict):
            result = [result]
        for entry in result:
            if isinstance(entry, dict) and "spec" in entry:
                entry["spec"] = normalize_spec_from_parse(entry.get("spec") or "")
                if not (entry.get("spec") or "").strip():
                    entry["spec"] = get_default_spec_for_item(entry.get("item") or "")
        _compute_boxes_remainder_from_total(result)
        if any(isinstance(e, dict) and "total" not in e for e in result):
            _fix_boxes_remainder_when_count_misread_as_boxes(result)
        return result
    except json.JSONDecodeError as e:
        st.error(format_error_display(e, "JSON解析"))
        st.text(f"レスポンス内容: {text[:500]}")
        return None
    except Exception as e:
        st.error(format_error_display(e, "画像解析"))
        return None

def parse_order_text(text: str, sender: str, subject: str, api_key: str) -> list:
    """メール本文（テキスト）を解析して注文データを抽出"""
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception:
            model = genai.GenerativeModel('gemini-pro')
            
    known_stores = get_known_stores()
    item_normalization = get_item_normalization()
    store_list = "、".join(known_stores)
    unit_lines, box_count_str, spec_master_section = _build_spec_master_prompt_sections()
    
    prompt = f"""
    メール本文から注文情報を抽出し、JSON形式で返してください。
    
    【送信者】{sender}
    【件名】{subject}
    
    【店舗名リスト（参考）】
    {store_list}
    ※リストになくても、文脈から店舗名と判断できる場合は抽出してください。
    
    【品目名の正規化ルール】
    {json.dumps(item_normalization, ensure_ascii=False, indent=2)}
    
    {spec_master_section}
    
    【計算ルール（1コンテナあたりの入数）】
    {unit_lines}
    
    【合計数量(total)の取り方】
    - 合計数量：メール内の「×」の後の数字を合計数量(total)とします。※「胡瓜バラ 50×4」のように「数×数」の表記の場合は、50×4＝200 として total に入れてください。
    - 箱数で受信する品目（{box_count_str}）のみ：「×」の後の数字を箱数とし、合計数量＝箱数×入数 として total に入れてください（例：4箱・入数30 → total=120）。箱数・端数は出力不要です（Python側で計算します）。
    
    【重要ルール】
    - 出力は純粋なJSONのみ (Markdown記法なし)。
    - unit と total には「数字のみ」を入れてください。
    - 日付情報が含まれている場合でも、今回の出力には含めず、注文明細のみ抽出してください。
    
    【出力JSON形式】
    [{{"store":"店舗名","item":"品目名","spec":"規格","unit":数字,"total":数字}}]
    
    【メール本文】
    {text}
    """
    
    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip()
        if '```json' in text_resp:
            text_resp = text_resp.split('```json')[1].split('```')[0].strip()
        elif '```' in text_resp:
            parts = text_resp.split('```')
            for part in parts:
                if '{' in part and '[' in part:
                    text_resp = part.strip()
                    break
        result = json.loads(text_resp)
        if isinstance(result, dict):
            result = [result]
        for entry in result:
            if isinstance(entry, dict) and "spec" in entry:
                entry["spec"] = normalize_spec_from_parse(entry.get("spec") or "")
                if not (entry.get("spec") or "").strip():
                    entry["spec"] = get_default_spec_for_item(entry.get("item") or "")
        _compute_boxes_remainder_from_total(result)
        if any(isinstance(e, dict) and "total" not in e for e in result):
            _fix_boxes_remainder_when_count_misread_as_boxes(result)
        return result
    except Exception as e:
        st.error(format_error_display(e, "テキスト解析"))
        return None

def validate_and_fix_order_data(order_data, auto_learn=True):
    if not order_data:
        return []
    validated_data = []
    errors = []
    learned_stores = []
    learned_items = []
    known_stores = get_known_stores()
    for i, entry in enumerate(order_data):
        store = entry.get('store', '').strip()
        item = entry.get('item', '').strip()
        validated_store = validate_store_name(store, auto_learn=auto_learn)
        if not validated_store and store:
            if auto_learn:
                validated_store = auto_learn_store(store)
                if validated_store not in learned_stores:
                    learned_stores.append(validated_store)
            else:
                errors.append(f"行{i+1}: 不明な店舗名「{store}」")
                for known_store in known_stores:
                    if any(char in store for char in known_store):
                        validated_store = known_store
                        break
        normalized_item = normalize_item_name(item, auto_learn=auto_learn)
        if not normalized_item and item:
            if auto_learn:
                normalized_item = auto_learn_item(item)
                if normalized_item not in learned_items:
                    learned_items.append(normalized_item)
            else:
                errors.append(f"行{i+1}: 品目名「{item}」を正規化できませんでした")
        unit = safe_int(entry.get('unit', 0))
        boxes = safe_int(entry.get('boxes', 0))
        remainder = safe_int(entry.get('remainder', 0))
        spec_for_lookup = (entry.get('spec') or '').strip() if entry.get('spec') is not None else ''
        if unit <= 0:
            looked_up = lookup_unit(normalized_item or item, spec_for_lookup, validated_store or store)
            if looked_up > 0:
                unit = looked_up
            else:
                item_setting = get_item_setting(normalized_item or item, spec_for_lookup)
                default_unit = item_setting.get("default_unit", 0)
                if default_unit > 0:
                    unit = default_unit
        effective_unit = get_effective_unit_size(normalized_item or item, spec_for_lookup)
        item_setting_for_boxes = get_item_setting(normalized_item or item, spec_for_lookup)
        receive_as_boxes = bool(item_setting_for_boxes.get("receive_as_boxes", False))
        if effective_unit > 0 and unit > 0 and unit < effective_unit and boxes == 0 and remainder == 0:
            boxes = unit
            unit = effective_unit
            remainder = 0
        elif receive_as_boxes and effective_unit > 0 and unit == effective_unit and boxes == 0 and 0 < remainder < effective_unit:
            # 平箱のみ: 「100×10」で10が箱数の場合の補正。春菊など個数品目では remainder は端数なので変換しない
            boxes = remainder
            remainder = 0
        if unit == 0 and boxes == 0 and remainder == 0:
            errors.append(f"行{i+1}: 数量が全て0です（店舗: {store}, 品目: {item}）")
        spec_value = entry.get('spec', '')
        if spec_value is None:
            spec_value = ''
        else:
            spec_value = str(spec_value).strip()
        if unit > 0:
            add_unit_if_new(normalized_item or item, spec_value, validated_store or store, unit)
        validated_data.append({
            'store': validated_store or store,
            'item': normalized_item or item,
            'spec': spec_value,
            'unit': unit,
            'boxes': boxes,
            'remainder': remainder
        })
    if auto_learn:
        if learned_stores:
            st.success(f"✨ 新しい店舗名を学習しました: {', '.join(learned_stores)}")
        if learned_items:
            st.success(f"✨ 新しい品目名を学習しました: {', '.join(learned_items)}")
    if errors:
        st.warning("⚠️ 検証で以下の問題が見つかりました:")
        for error in errors:
            st.write(f"- {error}")
    return validated_data
