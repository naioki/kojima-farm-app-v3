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
)

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
    item_settings_for_prompt = load_item_settings()
    box_count_items = get_box_count_items()
    unit_lines = "\n".join([f"- {name}: {s.get('default_unit', 0)}{s.get('unit_type', '袋')}/コンテナ" for name, s in sorted(item_settings_for_prompt.items()) if s.get("default_unit", 0) > 0])
    box_count_str = "、".join(box_count_items) if box_count_items else "（なし）"
    prompt = f"""
    画像を解析し、以下の厳密なルールに従ってJSONで返してください。
    
    【店舗名リスト（参考）】
    {store_list}
    ※上記リストにない店舗名も読み取ってください。
    
    【品目名の正規化ルール】
    {json.dumps(item_normalization, ensure_ascii=False, indent=2)}
    
    【重要ルール】
    1. 店舗名の後に「:」または改行がある場合、その後の行は全てその店舗の注文です
    2. 品目名がない行（例：「50×1」）は、直前の品目の続きとして処理してください
    3. 「/」で区切られた複数の注文は、同じ店舗・同じ品目として統合してください
    4. 「胡瓜バラ」と「胡瓜3本」は別の規格として扱ってください
    5. unit, boxes, remainderには「数字のみ」を入れてください
    
    【計算ルール（事前登録マスターデータ＝1コンテナあたりの入数）】
    {unit_lines}
    
    【最重要：総数 vs 箱数】
    - 「×数字」が総数の品目：boxes = 総数÷unit（切り捨て）, remainder = 総数 - unit×boxes で逆算してください。
    - 「×数字」が箱数の品目（以下のみ）：{box_count_str} → ×数字をそのままboxesにし、unitは上記の値、remainder=0 で出力してください。
    
    【出力JSON形式】
    [{{"store":"店舗名","item":"品目名","spec":"規格","unit":数字,"boxes":数字,"remainder":数字}}]
    
    【メール本文】
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
        return result
    except json.JSONDecodeError as e:
        st.error(f"JSON解析エラー: {e}")
        st.text(f"レスポンス内容: {text[:500]}")
        return None
    except Exception as e:
        st.error(f"画像解析エラー: {e}")
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
    item_settings_for_prompt = load_item_settings()
    unit_lines = "\n".join([f"- {name}: {s.get('default_unit', 0)}{s.get('unit_type', '袋')}/コンテナ" for name, s in sorted(item_settings_for_prompt.items()) if s.get("default_unit", 0) > 0])
    
    prompt = f"""
    メール本文から注文情報を抽出し、JSON形式で返してください。
    
    【送信者】{sender}
    【件名】{subject}
    
    【店舗名リスト（参考）】
    {store_list}
    ※リストになくても、文脈から店舗名と判断できる場合は抽出してください。
    
    【品目名の正規化ルール】
    {json.dumps(item_normalization, ensure_ascii=False, indent=2)}
    
    【計算ルール（1コンテナあたりの入数）】
    {unit_lines}
    
    【重要ルール】
    - 出力は純粋なJSONのみ (Markdown記法なし)。
    - unit, boxes, remainderには「数字のみ」を入れてください。
    - 「×数字」が総数の場合は boxes/remainder に分解し、箱数の場合は boxes に入れてください（文脈から判断）。
    - 日付情報が含まれている場合でも、今回の出力には含めず、注文明細のみ抽出してください。
    
    【出力JSON形式】
    [{{"store":"店舗名","item":"品目名","spec":"規格","unit":数字,"boxes":数字,"remainder":数字}}]
    
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
        return result
    except Exception as e:
        st.error(f"テキスト解析エラー: {e}")
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
        if effective_unit > 0 and unit > 0 and unit < effective_unit and boxes == 0 and remainder == 0:
            boxes = unit
            unit = effective_unit
            remainder = 0
        elif effective_unit > 0 and unit == effective_unit and boxes == 0 and 0 < remainder < effective_unit:
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
