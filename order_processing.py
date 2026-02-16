"""
注文データ処理モジュール
画像/テキスト解析、データ検証、正規化ロジックを担当

【致命的ルール】注文の「×」の直後の数字は合計数量（総数）。箱数ではない。
  例: 胡瓜3本×150 → total=150（誤り: total=4500）。春菊×20 → total=20（誤り: total=600）。
  詳細: docs/計算ロジックと品質保証.md の「致命的に守るべきルール」
"""
import json
import re
import time
import google.generativeai as genai
import streamlit as st # UIフィードバック用に一時的に維持
from PIL import Image
from typing import List, Dict, Optional, Any

from config_manager import (
    load_stores, auto_learn_store,
    load_items, auto_learn_item,
    load_item_settings, get_box_count_items,
    lookup_unit, get_item_setting, add_unit_if_new,
    get_effective_unit_size, extract_unit_size_from_spec,
    load_item_spec_master,
    get_default_spec_for_item,
)
from error_display_util import format_error_display
from box_remainder_calc import total_to_boxes_remainder, calculate_inventory

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
    （受信方法分岐は _compute_from_input_num_by_reception で実施。互換用に残す）
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
            boxes, remainder = total_to_boxes_remainder(total, unit)
            entry["boxes"] = boxes
            entry["remainder"] = remainder


def _compute_from_input_num_by_reception(entries: list) -> None:
    """
    マスタの「受信方法」（総数/箱数）に基づき、注文の「×」の後ろの数値(input_num)から
    合計数量・箱数・端数を算出して entry に反映する。
    - 総数: input_num = 合計数量 → boxes = total // unit, remainder = total % unit
    - 箱数: input_num = 箱数 → total = boxes * unit, remainder = 0
    - バラで「100本×7」など入数明記時: unit_override を使い total = 100*7
    entry に input_num があればそれを使用。なければ total から逆算（後方互換）。
    """
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        item = (entry.get("item") or "").strip()
        spec = (entry.get("spec") or "").strip()
        normalized = normalize_item_name(item, auto_learn=False)
        setting = get_item_setting(normalized or item, spec)
        master_unit = int(setting.get("default_unit", 0)) or 0
        receive_as_boxes = bool(setting.get("receive_as_boxes", False))
        unit_override = entry.get("unit_from_text")
        if unit_override is not None:
            unit_override = safe_int(unit_override)
        # 胡瓜バラで「100本×7」「50本×1」のとき、AIが unit_from_text を返さない場合に spec から入数を補完（受信方法は箱数なので「×」後＝箱数）
        if unit_override is None and receive_as_boxes and spec in ("100本", "50本"):
            u_from_spec = extract_unit_size_from_spec(spec)
            if u_from_spec > 0:
                unit_override = u_from_spec

        input_num = entry.get("input_num")
        if input_num is not None:
            input_num = safe_int(input_num)
        else:
            total = safe_int(entry.get("total", 0))
            # 受信方法「箱数」: 「×」の後は箱数。total が入数で割り切れるときは箱数＝total÷入数、そうでないときは total を箱数と解釈（AIが箱数を total に入れた場合）
            effective_unit = int(unit_override) if (unit_override is not None and int(unit_override) > 0) else master_unit
            if receive_as_boxes and effective_unit > 0 and total > 0:
                if total % effective_unit == 0:
                    input_num = total // effective_unit
                else:
                    # 例: 胡瓜バラ100本×7 で AI が total=7 と返した場合 → 7 を箱数として扱う
                    input_num = total
            else:
                input_num = total

        if master_unit <= 0 and (unit_override is None or unit_override <= 0):
            entry["boxes"] = 0
            entry["remainder"] = input_num
            entry["total"] = input_num
            entry["unit"] = safe_int(entry.get("unit", 0)) or 0
            continue

        total, boxes, remainder, unit_used = calculate_inventory(
            input_num, master_unit, receive_as_boxes, unit_override
        )
        entry["total"] = total
        entry["boxes"] = boxes
        entry["remainder"] = remainder
        entry["unit"] = unit_used


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
            entry["boxes"], entry["remainder"] = total_to_boxes_remainder(total, unit)


def _fix_total_when_ai_sent_boxes_times_unit(entries: list) -> None:
    """
    AIが「×」の後の数字を箱数と誤解し、total=箱数×入数 で返した場合にのみ補正する。
    例：胡瓜3本×150 → 正しくは total=150。AIが total=4500(150*30) と返したら total=150 に直す。
    注意: total=300(箱数10×入数30) や total=500(箱数10×入数50) は正しい値なので補正しない。
    条件: total > 1000 かつ total == unit * boxes かつ boxes が 10～1000 のときだけ補正（total が明らかに大きい場合のみ）。
    """
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        total = safe_int(entry.get("total", 0))
        unit = safe_int(entry.get("unit", 0))
        boxes = safe_int(entry.get("boxes", 0))
        remainder = safe_int(entry.get("remainder", 0))
        if unit <= 0 or total <= 0 or remainder != 0:
            continue
        item = (entry.get("item") or "").strip()
        spec = (entry.get("spec") or "").strip()
        normalized_item = normalize_item_name(item, auto_learn=False)
        setting = get_item_setting(normalized_item or item, spec)
        if setting.get("receive_as_boxes", False):
            continue
        # total が 箱数×入数 の誤りと判断できるのは「total が 1000 を超える」場合のみ。300・500 などは正しい合計なので触らない
        if total > 1000 and total == unit * boxes and 10 <= boxes <= 1000:
            entry["total"] = boxes
            entry["boxes"], entry["remainder"] = total_to_boxes_remainder(boxes, unit)


def _fix_known_misread_patterns(entries: list) -> None:
    """
    実運用で判明した誤読パターンを明示的に補正する。
    1) 青葉台 / 胡瓜 / バラ: 「50本×1」→ 入数50・箱数1・合計50。入数100固定をやめ、50本×1の意図を反映。
    2) 習志野台 / 長ネギ / 2本: 「2本×80」が 30×21+10=640 になっている → 合計80に修正。
    注: 胡瓜3本などマスタで「1コンテナあたりの入数」が決まっている品目は、入数は常にマスタ値（30）、箱数は合計数量÷入数で算出する（「3本×50」でも入数30・箱数5）。
    """
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        store = (entry.get("store") or "").strip()
        item = (entry.get("item") or "").strip()
        spec = (entry.get("spec") or "").strip()
        total = safe_int(entry.get("total", 0))
        unit = safe_int(entry.get("unit", 0))
        boxes = safe_int(entry.get("boxes", 0))
        remainder = safe_int(entry.get("remainder", 0))
        normalized_item = normalize_item_name(item, auto_learn=False)

        # 1) 青葉台 胡瓜 バラ: 「50本×1」→ 入数50, 箱数1, 合計50（入数100で固定しない）
        if "青葉台" in store and (normalized_item == "胡瓜" or "胡瓜" in (normalized_item or item)) and (spec == "バラ" or "バラ" in spec):
            if total == 5000 and unit == 100 and boxes == 50 and remainder == 0:
                entry["total"] = 50
                entry["unit"] = 50
                entry["boxes"] = 1
                entry["remainder"] = 0
            elif total == 100 and unit == 100 and boxes == 1 and remainder == 0:
                entry["total"] = 50
                entry["unit"] = 50
                entry["boxes"] = 1
                entry["remainder"] = 0
            elif total == 50 and unit == 100 and boxes == 0 and remainder == 50:
                entry["unit"] = 50
                entry["boxes"] = 1
                entry["remainder"] = 0

        # 2) 習志野台 長ネギ 2本: 「2本×80」が 30×21+10=640 と誤計算 → total=80 に
        if "習志野台" in store and (normalized_item == "長ネギ" or "ネギ" in (normalized_item or item)) and (spec == "2本" or spec == "２本"):
            if total == 640 and unit == 30 and boxes == 21 and remainder == 10:
                entry["total"] = 80
                entry["boxes"], entry["remainder"] = total_to_boxes_remainder(80, 30)


def normalize_spec_from_parse(spec_str: str) -> str:
    """
    メール・画像解析で得た規格を、品目名管理マスタに合わせて正規化する。
    - ばら / バラ → バラ
    - 平箱 → 平箱
    - N本（数字+本）→ そのまま（3本, 2本, 50本など）
    - 2-3株 → 2~3株（マスタ表記に統一）
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
    # 青梗菜の規格表記ゆれ（2-3株 → 2~3株）
    if s in ("2-3株", "2‐3株", "2ー3株"):
        return "2~3株"
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

def _generate_content_with_retry(model, contents, max_retries=2):
    """429 クォータ超過時はメッセージ内の待機秒数で待ってリトライする。"""
    last_err = None
    for attempt in range(max_retries + 1):
        try:
            return model.generate_content(contents)
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if attempt < max_retries and ("429" in err_str or "quota" in err_str or "rate" in err_str):
                wait_sec = 10
                m = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", str(e), re.IGNORECASE)
                if m:
                    wait_sec = min(60, max(1, float(m.group(1))))
                time.sleep(wait_sec)
                continue
            raise
    raise last_err

def parse_order_image(image: Image.Image, api_key: str) -> list:
    genai.configure(api_key=api_key)
    # コスト優先: 2.5-flash-lite（最安）→ 2.5-flash → 1.5-pro → pro-vision
    try:
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
    except Exception:
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
        except Exception:
            try:
                model = genai.GenerativeModel('gemini-1.5-pro')
            except Exception:
                model = genai.GenerativeModel('gemini-pro-vision')
    known_stores = get_known_stores()
    item_normalization = get_item_normalization()
    store_list = "、".join(known_stores)
    unit_lines, box_count_str, spec_master_section = _build_spec_master_prompt_sections()
    # トークン削減: 冗長表現を削り、ルール・品質は維持
    # 【致命】「×」の後＝合計数量。プロンプトに「×の後＝箱数」や total=個数×入数 の誤った例を書かないこと。
    norm_json = json.dumps(item_normalization, ensure_ascii=False)
    prompt = f"""画像を解析し、厳密に以下のルールでJSONのみ返す。

【読み取り】写っている文字・数字のみ。推測で補完しない。店舗・品目・規格・数量は表記と一致させる。読みにくい部分は見えた通りか控えめに。
【店舗】{store_list}（リスト外も読み取る）
【品目正規化】{norm_json}
{spec_master_section}
【ルール】1) 店舗名の「:」以降はその店舗の注文 2) 品目なし行は直前の品目の続き 3) 「/」区切りは同店舗・同品目で統合 4) 胡瓜バラと胡瓜3本は別規格 5) unit/totalは数字のみ（箱数・端数は出力しない）
【入数】{unit_lines}
【total・重要】「×」の直後の数字はその品目の「合計数量（総数）」です。箱数ではない。その数字をそのまま total に入れる。
・胡瓜3本×150 → total=150（150は総数。150箱ではない）
・春菊×20 → total=20
・青梗菜×15 → total=15
・ネギ2本×120 → total=120
例外1) 箱数で受信の品目（{box_count_str}）のみ：「×」後を箱数とし total=箱数×入数。例：胡瓜平箱×1→total=50。
例外2) 「胡瓜バラ 50×4」のように「数×数」の掛け算表記のときは 50×4=200 を total に。
例外3) 規格バラで入数が明記されている場合のみ unit_from_text と input_num を入れる。例：「100本×7」→ unit_from_text:100, input_num:7, total=700。「50本×1」→ unit_from_text:50, input_num:1, total=50。
【出力】[{{"store":"店舗","item":"品目","spec":"規格","unit":数,"total":数,"input_num":数}}]。input_numは「×」の直後の数値。総数品目ではinput_num=合計数量、箱数品目（{box_count_str}）ではinput_num=箱数。バラでN本×Mのときは必ず unit_from_text:N, input_num:M を入れる。
全店舗・全品目を漏れなく。長ネギ2本は入数30で計算すること。"""
    try:
        response = _generate_content_with_retry(model, [prompt, image])
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
        _compute_from_input_num_by_reception(result)
        _fix_total_when_ai_sent_boxes_times_unit(result)
        _fix_known_misread_patterns(result)
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
    # コスト優先: 2.5-flash-lite → 2.5-flash → 1.5-pro → gemini-pro
    try:
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
    except Exception:
        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
        except Exception:
            try:
                model = genai.GenerativeModel('gemini-1.5-pro')
            except Exception:
                model = genai.GenerativeModel('gemini-pro')
    known_stores = get_known_stores()
    item_normalization = get_item_normalization()
    store_list = "、".join(known_stores)
    unit_lines, box_count_str, spec_master_section = _build_spec_master_prompt_sections()
    # 【致命】「×」の後＝合計数量。total=個数×入数 の誤った例をプロンプトに書かないこと。
    norm_json = json.dumps(item_normalization, ensure_ascii=False)
    prompt = f"""メール本文から注文のみ抽出し、JSONのみ返す。送信者:{sender} 件名:{subject}
【店舗】{store_list}（文脈から判断可）
【品目正規化】{norm_json}
{spec_master_section}
【入数】{unit_lines}
【total・重要】「×」の直後の数字はその品目の「合計数量（総数）」です。箱数ではない。その数字をそのまま total に入れる。
・胡瓜3本×150→total=150 ・春菊×20→total=20 ・青梗菜×15→total=15 ・ネギ2本×120→total=120
例外1) 箱数で受信（{box_count_str}）のみ：「×」後を箱数とし total=箱数×入数。例：胡瓜平箱×1→total=50。
例外2) 「50×4」の掛け算表記のときは 50×4=200 を total に。春菊・青梗菜は規格省略可。長ネギ2本はunit=30。日付は出力しない。
例外3) 規格バラで入数が明記されている場合のみ unit_from_text と input_num を入れる。例：「100本×7」→ unit_from_text:100, input_num:7, total=700。「50本×1」→ unit_from_text:50, input_num:1, total=50。
【出力】[{{"store":"店舗","item":"品目","spec":"規格","unit":数,"total":数,"input_num":数}}]（Markdownなし）。input_numは「×」の直後の数値。総数ではinput_num=合計数量、箱数品目（{box_count_str}）ではinput_num=箱数。バラでN本×Mのときは必ず unit_from_text:N, input_num:M を入れる。
【本文】
{text}"""
    
    try:
        response = _generate_content_with_retry(model, prompt)
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
        _compute_from_input_num_by_reception(result)
        _fix_total_when_ai_sent_boxes_times_unit(result)
        _fix_known_misread_patterns(result)
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
            # unit に総数が入っていた場合: 箱数＝総数÷入数 の商、端数＝余りで再計算
            total_as_count = unit
            unit = effective_unit
            boxes, remainder = total_to_boxes_remainder(total_as_count, unit)
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
