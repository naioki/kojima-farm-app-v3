"""
設定管理モジュール
店舗名・品目名をJSONファイルで動的に管理
規格名から入数（unit_size）を抽出する正規表現ロジックを含む。
"""
import json
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Any

# 規格名に含まれる入数（本数・袋数）を抽出する正規表現パターン（優先順）
# 例: バラ100, 3本, 平箱（30本）, 30本入り
SPEC_UNIT_SIZE_PATTERNS = [
    re.compile(r"バラ\s*(\d+)", re.IGNORECASE),           # バラ100, バラ 100
    re.compile(r"平箱\s*[（(]\s*(\d+)", re.IGNORECASE),    # 平箱（30本）, 平箱(30)
    re.compile(r"[（(]\s*(\d+)\s*[本)）]", re.IGNORECASE), # （30本）, (30本)
    re.compile(r"(\d+)\s*本入り", re.IGNORECASE),         # 30本入り
    re.compile(r"(\d+)\s*本\b", re.IGNORECASE),          # 3本, 30本
    re.compile(r"(\d+)\s*袋\b", re.IGNORECASE),           # 10袋
]

CONFIG_DIR = Path("config")
STORES_FILE = CONFIG_DIR / "stores.json"
ITEMS_FILE = CONFIG_DIR / "items.json"
UNITS_FILE = CONFIG_DIR / "units.json"
ITEM_SETTINGS_FILE = CONFIG_DIR / "item_settings.json"
ITEM_SPEC_MASTER_FILE = CONFIG_DIR / "item_spec_master.json"

DEFAULT_STORES = ["鎌ケ谷", "五香", "八柱", "青葉台", "咲が丘", "習志野台", "八千代台"]

DEFAULT_ITEMS = {
    "青梗菜": ["青梗菜", "チンゲン菜", "ちんげん菜", "チンゲンサイ", "ちんげんさい"],
    "胡瓜": ["胡瓜", "きゅうり", "キュウリ", "胡瓜（袋）"],
    "胡瓜平箱": ["胡瓜平箱", "胡瓜平箱"],
    "胡瓜バラ": ["胡瓜バラ", "きゅうりバラ", "キュウリバラ", "胡瓜ばら"],
    "長ネギ": ["長ネギ", "ネギ", "ねぎ", "長ねぎ", "長ねぎ（袋）"],
    "長ねぎバラ": ["長ねぎバラ", "長ネギバラ", "ネギバラ", "ねぎバラ", "長ねぎばら"],
    "春菊": ["春菊", "しゅんぎく", "シュンギク"]
}


def ensure_config_dir():
    CONFIG_DIR.mkdir(exist_ok=True)


def load_stores() -> List[str]:
    ensure_config_dir()
    if STORES_FILE.exists():
        try:
            with open(STORES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('stores', DEFAULT_STORES)
        except Exception:
            return DEFAULT_STORES
    else:
        save_stores(DEFAULT_STORES)
        return DEFAULT_STORES


def save_stores(stores: List[str]):
    ensure_config_dir()
    with open(STORES_FILE, 'w', encoding='utf-8') as f:
        json.dump({'stores': stores}, f, ensure_ascii=False, indent=2)


def add_store(store_name: str) -> bool:
    stores = load_stores()
    if store_name not in stores:
        stores.append(store_name)
        save_stores(stores)
        return True
    return False


def remove_store(store_name: str) -> bool:
    stores = load_stores()
    if store_name in stores:
        stores.remove(store_name)
        save_stores(stores)
        return True
    return False


def load_items() -> Dict[str, List[str]]:
    ensure_config_dir()
    if ITEMS_FILE.exists():
        try:
            with open(ITEMS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for k, v in DEFAULT_ITEMS.items():
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            return DEFAULT_ITEMS.copy()
    else:
        save_items(DEFAULT_ITEMS)
        return DEFAULT_ITEMS.copy()


def save_items(items: Dict[str, List[str]]):
    ensure_config_dir()
    with open(ITEMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_item_variant(normalized_name: str, variant: str):
    items = load_items()
    if normalized_name not in items:
        items[normalized_name] = []
    if variant not in items[normalized_name]:
        items[normalized_name].append(variant)
    save_items(items)


def add_new_item(normalized_name: str, variants: Optional[List[str]] = None):
    items = load_items()
    if normalized_name not in items:
        items[normalized_name] = variants or [normalized_name]
        save_items(items)
        return True
    return False


def remove_item(normalized_name: str) -> bool:
    items = load_items()
    if normalized_name in items:
        del items[normalized_name]
        save_items(items)
        return True
    return False


def auto_learn_store(store_name: str) -> str:
    stores = load_stores()
    store_name = store_name.strip()
    for existing_store in stores:
        if existing_store in store_name or store_name in existing_store:
            return existing_store
    if store_name and store_name not in stores:
        add_store(store_name)
    return store_name


def auto_learn_item(item_name: str) -> str:
    items = load_items()
    item_name = item_name.strip()
    for normalized, variants in items.items():
        if item_name in variants or any(variant in item_name for variant in variants):
            return normalized
    if item_name:
        add_new_item(item_name, [item_name])
    return item_name


def _units_key(item: str, spec: str, store: str) -> str:
    def n(v):
        return (v or "").strip().replace(" ", "")
    return f"{n(item)}|{n(spec)}|{n(store)}"


def load_units() -> Dict[str, int]:
    ensure_config_dir()
    if UNITS_FILE.exists():
        try:
            with open(UNITS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return {k: int(v) for k, v in data.items() if v}
                return {}
        except Exception:
            return {}
    return {}


def save_units(units: Dict[str, int]):
    ensure_config_dir()
    with open(UNITS_FILE, 'w', encoding='utf-8') as f:
        json.dump(units, f, ensure_ascii=False, indent=2)


def lookup_unit(item: str, spec: str, store: str) -> int:
    units = load_units()
    return units.get(_units_key(item, spec, store), 0)


def add_unit_if_new(item: str, spec: str, store: str, unit: int) -> bool:
    if unit <= 0:
        return False
    units = load_units()
    key = _units_key(item, spec, store)
    if key in units:
        return False
    units[key] = unit
    save_units(units)
    return True


def set_unit(item: str, spec: str, store: str, unit: int) -> None:
    if unit <= 0:
        return
    units = load_units()
    units[_units_key(item, spec, store)] = unit
    save_units(units)


def initialize_default_units():
    units = load_units()
    updated = False
    default_unit_map = {
        ("胡瓜", ""): 30, ("胡瓜平箱", ""): 30, ("胡瓜バラ", ""): 100,
        ("長ネギ", ""): 50, ("長ねぎバラ", ""): 50, ("春菊", ""): 30, ("青梗菜", ""): 20,
    }
    stores = load_stores()
    for (item, spec), unit in default_unit_map.items():
        for store in stores:
            key = _units_key(item, spec, store)
            if key not in units:
                units[key] = unit
                updated = True
    if updated:
        save_units(units)


DEFAULT_ITEM_SETTINGS = {
    "胡瓜": {"default_unit": 30, "unit_type": "袋", "receive_as_boxes": False, "min_shipping_unit": 30},
    "胡瓜平箱": {"default_unit": 30, "unit_type": "袋", "receive_as_boxes": True, "min_shipping_unit": 30},
    "胡瓜バラ": {"default_unit": 100, "unit_type": "本", "receive_as_boxes": False, "min_shipping_unit": 30},
    "長ネギ": {"default_unit": 50, "unit_type": "本", "receive_as_boxes": False, "min_shipping_unit": 1},
    "長ねぎバラ": {"default_unit": 50, "unit_type": "本", "receive_as_boxes": False, "min_shipping_unit": 1},
    "春菊": {"default_unit": 30, "unit_type": "袋", "receive_as_boxes": False, "min_shipping_unit": 1},
    "青梗菜": {"default_unit": 20, "unit_type": "袋", "receive_as_boxes": False, "min_shipping_unit": 1},
}


def load_item_settings() -> Dict[str, Dict[str, Any]]:
    ensure_config_dir()
    if ITEM_SETTINGS_FILE.exists():
        try:
            with open(ITEM_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged = DEFAULT_ITEM_SETTINGS.copy()
                    merged.update(data)
                    for key in ["長ネギ", "長ねぎバラ", "長ネギバラ"]:
                        if key in merged:
                            merged[key] = {**merged[key], "default_unit": 50, "unit_type": "本"}
                    for key in list(merged.keys()):
                        merged[key] = {**merged[key], "receive_as_boxes": merged[key].get("receive_as_boxes", DEFAULT_ITEM_SETTINGS.get(key, {}).get("receive_as_boxes", False))}
                    save_item_settings(merged)
                    return merged
                return DEFAULT_ITEM_SETTINGS.copy()
        except Exception:
            save_item_settings(DEFAULT_ITEM_SETTINGS)
            return DEFAULT_ITEM_SETTINGS.copy()
    else:
        save_item_settings(DEFAULT_ITEM_SETTINGS)
        return DEFAULT_ITEM_SETTINGS.copy()


def save_item_settings(settings: Dict[str, Dict[str, Any]]):
    ensure_config_dir()
    with open(ITEM_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_item_spec_master() -> List[Dict[str, Any]]:
    """品目+規格ごとのマスタ行を返す。なければ item_settings から生成して保存する。"""
    ensure_config_dir()
    if ITEM_SPEC_MASTER_FILE.exists():
        try:
            with open(ITEM_SPEC_MASTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data
        except Exception:
            pass
    settings = load_item_settings()
    rows = []
    for name, s in settings.items():
        rows.append({
            "品目": name,
            "規格": "",
            "default_unit": s.get("default_unit", 0),
            "unit_type": s.get("unit_type", "袋"),
            "receive_as_boxes": s.get("receive_as_boxes", False),
            "min_shipping_unit": s.get("min_shipping_unit", 0),
        })
    save_item_spec_master(rows)
    return rows


def save_item_spec_master(rows: List[Dict[str, Any]]) -> None:
    """品目+規格マスタを保存し、規格が空の行で item_settings を同期する。"""
    ensure_config_dir()
    with open(ITEM_SPEC_MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    settings = load_item_settings()
    for row in rows:
        item = (row.get("品目") or "").strip()
        spec = (row.get("規格") or "").strip()
        if item and spec == "":
            settings[item] = {
                "default_unit": int(row.get("default_unit", 0)) or 30,
                "unit_type": (row.get("unit_type") or "袋").strip() or "袋",
                "receive_as_boxes": bool(row.get("receive_as_boxes", False)),
                "min_shipping_unit": int(row.get("min_shipping_unit", 0)) or 0,
            }
    save_item_settings(settings)


def get_item_setting(item: str, spec: Optional[str] = None) -> Dict[str, Any]:
    """品目（と規格）に一致する設定を返す。spec は省略可（その場合は規格なしを優先）。"""
    spec_s = (spec or "").strip()
    rows = load_item_spec_master()
    for r in rows:
        if (r.get("品目") or "").strip() != (item or "").strip():
            continue
        r_spec = (r.get("規格") or "").strip()
        if r_spec == spec_s:
            return {
                "default_unit": int(r.get("default_unit", 0)) or 0,
                "unit_type": (r.get("unit_type") or "袋").strip() or "袋",
                "receive_as_boxes": bool(r.get("receive_as_boxes", False)),
                "min_shipping_unit": int(r.get("min_shipping_unit", 0)) or 0,
            }
    if spec_s != "":
        for r in rows:
            if (r.get("品目") or "").strip() == (item or "").strip() and (r.get("規格") or "").strip() == "":
                return {
                    "default_unit": int(r.get("default_unit", 0)) or 0,
                    "unit_type": (r.get("unit_type") or "袋").strip() or "袋",
                    "receive_as_boxes": bool(r.get("receive_as_boxes", False)),
                    "min_shipping_unit": int(r.get("min_shipping_unit", 0)) or 0,
                }
    settings = load_item_settings()
    if item in settings:
        s = settings[item].copy()
        s.setdefault("receive_as_boxes", False)
        s.setdefault("min_shipping_unit", 0)
        return s
    return {"default_unit": 0, "unit_type": "袋", "receive_as_boxes": False, "min_shipping_unit": 0}


def extract_unit_size_from_spec(spec_name: Optional[str]) -> int:
    """
    規格名に含まれる数値（入数）を正規表現で抽出する。
    例: 「バラ100」→100, 「3本」→3, 「平箱（30本）」→30
    該当なしの場合は 0 を返す。
    """
    if spec_name is None or not isinstance(spec_name, str):
        return 0
    s = spec_name.strip()
    if not s:
        return 0
    for pat in SPEC_UNIT_SIZE_PATTERNS:
        m = pat.search(s)
        if m:
            try:
                n = int(m.group(1))
                return max(1, min(n, 9999))
            except (ValueError, IndexError):
                continue
    return 0


def get_effective_unit_size(item: str, spec: Optional[str] = None) -> int:
    """
    合計数量計算用の有効入数（unit_size）を返す。
    優先順位: (1) 規格マスタの default_unit (2) 規格名から抽出した数値
    """
    spec_s = (spec or "").strip()
    setting = get_item_setting(item, spec_s)
    master_unit = int(setting.get("default_unit", 0)) or 0
    if master_unit > 0:
        return master_unit
    from_spec = extract_unit_size_from_spec(spec_s)
    if from_spec > 0:
        return from_spec
    return 0


def get_min_shipping_unit(item: str, spec: Optional[str] = None) -> int:
    """品目（と規格）ごとの最小出荷単位。未設定なら 0（チェックしない）。"""
    setting = get_item_setting(item, spec)
    return int(setting.get("min_shipping_unit", 0)) or 0


def get_known_specs_for_item(item: str) -> List[str]:
    """品目に対するマスタ登録済み規格のリスト（空文字＝規格なし含む）。"""
    rows = load_item_spec_master()
    return [(r.get("規格") or "").strip() for r in rows if (r.get("品目") or "").strip() == (item or "").strip()]


def is_spec_in_master(item: str, spec: str) -> bool:
    """AI解析結果の規格がマスタに登録されているか。空規格はマスタに「規格なし」があればTrue。"""
    spec_s = (spec or "").strip()
    known = get_known_specs_for_item(item)
    if not known:
        return False
    return spec_s in known


def set_item_setting(item: str, default_unit: int, unit_type: str, receive_as_boxes: bool = None):
    settings = load_item_settings()
    existing = settings.get(item, {})
    settings[item] = {
        "default_unit": default_unit,
        "unit_type": unit_type,
        "receive_as_boxes": receive_as_boxes if receive_as_boxes is not None else existing.get("receive_as_boxes", False),
    }
    save_item_settings(settings)


def set_item_receive_as_boxes(item: str, receive_as_boxes: bool):
    settings = load_item_settings()
    if item not in settings:
        settings[item] = {"default_unit": 0, "unit_type": "袋", "receive_as_boxes": receive_as_boxes}
    else:
        settings[item]["receive_as_boxes"] = receive_as_boxes
    save_item_settings(settings)


def get_box_count_items() -> List[str]:
    settings = load_item_settings()
    return [name for name, s in settings.items() if s.get("receive_as_boxes", False)]


def remove_item_setting(item: str):
    settings = load_item_settings()
    if item in settings:
        del settings[item]
        save_item_settings(settings)
