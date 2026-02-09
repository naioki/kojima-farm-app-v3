"""
設定管理モジュール
店舗名・品目名をJSONファイルで動的に管理
"""
import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any

CONFIG_DIR = Path("config")
STORES_FILE = CONFIG_DIR / "stores.json"
ITEMS_FILE = CONFIG_DIR / "items.json"
UNITS_FILE = CONFIG_DIR / "units.json"
ITEM_SETTINGS_FILE = CONFIG_DIR / "item_settings.json"

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
    "胡瓜": {"default_unit": 30, "unit_type": "袋", "receive_as_boxes": False},
    "胡瓜平箱": {"default_unit": 30, "unit_type": "袋", "receive_as_boxes": True},
    "胡瓜バラ": {"default_unit": 100, "unit_type": "本", "receive_as_boxes": False},
    "長ネギ": {"default_unit": 50, "unit_type": "本", "receive_as_boxes": False},
    "長ねぎバラ": {"default_unit": 50, "unit_type": "本", "receive_as_boxes": False},
    "春菊": {"default_unit": 30, "unit_type": "袋", "receive_as_boxes": False},
    "青梗菜": {"default_unit": 20, "unit_type": "袋", "receive_as_boxes": False},
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


def get_item_setting(item: str) -> Dict[str, Any]:
    settings = load_item_settings()
    if item in settings:
        s = settings[item].copy()
        s.setdefault("receive_as_boxes", False)
        return s
    return {"default_unit": 0, "unit_type": "袋", "receive_as_boxes": False}


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
