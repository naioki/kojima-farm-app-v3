"""
設定管理モジュール
品目マスタは Google Sheets を優先し、ローカル JSON をフォールバックとして使用。
店舗名・入数キャッシュはローカル JSON で管理。
規格名から入数（unit_size）を抽出する正規表現ロジックを含む。
"""
import json
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Any

# Sheets 連携（利用可能な場合のみ）
try:
    import sheets_config as _sc
except ImportError:
    _sc = None

# 規格名に含まれる入数（本数・袋数）を抽出する正規表現パターン（優先順）
SPEC_UNIT_SIZE_PATTERNS = [
    re.compile(r"バラ\s*(\d+)", re.IGNORECASE),
    re.compile(r"平箱\s*[（(]\s*(\d+)", re.IGNORECASE),
    re.compile(r"[（(]\s*(\d+)\s*[本)）]", re.IGNORECASE),
    re.compile(r"(\d+)\s*本入り", re.IGNORECASE),
    re.compile(r"(\d+)\s*本\b", re.IGNORECASE),
    re.compile(r"(\d+)\s*袋\b", re.IGNORECASE),
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
    "胡瓜平箱": ["胡瓜平箱"],
    "胡瓜バラ(100本)": ["胡瓜バラ", "きゅうりバラ", "キュウリバラ", "胡瓜ばら"],
    "胡瓜バラ(50本)": ["胡瓜バラ50本"],
    "長ネギ": ["長ネギ", "ネギ", "ねぎ", "長ねぎ", "長ねぎ（袋）"],
    "長ねぎバラ": ["長ねぎバラ", "長ネギバラ", "ネギバラ", "ねぎバラ", "長ねぎばら"],
    "春菊": ["春菊", "しゅんぎく", "シュンギク"]
}

DEFAULT_ITEM_SETTINGS = {
    "胡瓜": {"default_unit": 30, "unit_type": "袋", "receive_as_boxes": False, "min_shipping_unit": 30},
    "胡瓜平箱": {"default_unit": 50, "unit_type": "袋", "receive_as_boxes": True, "min_shipping_unit": 50},
    "胡瓜バラ(100本)": {"default_unit": 100, "unit_type": "本", "receive_as_boxes": True, "min_shipping_unit": 0},
    "胡瓜バラ(50本)": {"default_unit": 50, "unit_type": "本", "receive_as_boxes": True, "min_shipping_unit": 0},
    "長ネギ": {"default_unit": 30, "unit_type": "本", "receive_as_boxes": False, "min_shipping_unit": 1},
    "長ねぎバラ": {"default_unit": 50, "unit_type": "本", "receive_as_boxes": False, "min_shipping_unit": 1},
    "春菊": {"default_unit": 30, "unit_type": "袋", "receive_as_boxes": False, "min_shipping_unit": 1},
    "青梗菜": {"default_unit": 20, "unit_type": "袋", "receive_as_boxes": False, "min_shipping_unit": 1},
}

# 品目+規格の複合名ルックアップ
ITEM_SPEC_COMPOSITE_LOOKUP = {
    ("胡瓜", "バラ"): "胡瓜バラ(100本)",
    ("胡瓜", "平箱"): "胡瓜平箱",
    ("長ネギ", "バラ"): "長ねぎバラ",
    ("長ねぎ", "バラ"): "長ねぎバラ",
}


# ================================================================
# Sheets 利用可否の判定
# ================================================================

def _sheets_available() -> bool:
    """sheets_config がインポート済みかつ初期化済みかどうか。"""
    return _sc is not None and _sc.is_available()


# ================================================================
# ユーティリティ
# ================================================================

def ensure_config_dir():
    CONFIG_DIR.mkdir(exist_ok=True)


# ================================================================
# 店舗管理（JSON のまま）
# ================================================================

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


def auto_learn_store(store_name: str) -> str:
    stores = load_stores()
    store_name = store_name.strip()
    for existing_store in stores:
        if existing_store in store_name or store_name in existing_store:
            return existing_store
    if store_name and store_name not in stores:
        add_store(store_name)
    return store_name


# ================================================================
# 品目マスタ（Sheets 優先 → JSON フォールバック）
# ================================================================

def load_item_spec_master() -> List[Dict[str, Any]]:
    """品目+規格ごとのマスタ行を返す。Sheets 接続時は Sheets から読み込む。"""
    if _sheets_available():
        rows = _sc.load_master()
        if rows:
            return _sc.sheets_to_spec_master(rows)
    # JSON フォールバック
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
        default_spec = get_default_spec_for_item(name)
        rows.append({
            "品目": name,
            "規格": default_spec,
            "default_unit": s.get("default_unit", 0),
            "unit_type": s.get("unit_type", "袋"),
            "receive_as_boxes": s.get("receive_as_boxes", False),
            "min_shipping_unit": s.get("min_shipping_unit", 0),
        })
    _save_item_spec_master_json(rows)
    return rows


def save_item_spec_master(rows: List[Dict[str, Any]]) -> None:
    """品目+規格マスタを保存。Sheets 接続時は Sheets に書き込む。"""
    if _sheets_available():
        # 現在の Sheets データから別表記を取得して保持
        current_sheets = _sc.load_master(force=True)
        alt_lookup = {}
        for r in current_sheets:
            item = (r.get("品目") or "").strip()
            if item:
                alt_lookup[item] = r.get("別表記", "")
        # legacy 形式 → Sheets 形式に変換（別表記を保持）
        sheets_rows = []
        for r in rows:
            item = (r.get("品目") or "").strip()
            sheets_rows.append({
                "品目": item,
                "規格": (r.get("規格") or "").strip(),
                "別表記": alt_lookup.get(item, ""),
                "入数": int(r.get("default_unit", 0)) or 0,
                "単位": (r.get("unit_type") or "袋").strip() or "袋",
                "受信方法": "箱数" if r.get("receive_as_boxes") else "総数",
                "最小出荷単位": int(r.get("min_shipping_unit", 0)) or 0,
            })
        _sc.save_master(sheets_rows)
        return
    # JSON フォールバック
    _save_item_spec_master_json(rows)


def _save_item_spec_master_json(rows: List[Dict[str, Any]]) -> None:
    """JSON ファイルに品目+規格マスタを保存（フォールバック用）。"""
    ensure_config_dir()
    tmp_path = ITEM_SPEC_MASTER_FILE.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, ITEM_SPEC_MASTER_FILE)
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


# ================================================================
# 品目名（バリアント）管理
# ================================================================

def load_items() -> Dict[str, List[str]]:
    """品目名 → バリアント一覧。Sheets 接続時は Sheets の別表記列から導出。"""
    if _sheets_available():
        rows = _sc.load_master()
        if rows:
            result = _sc.sheets_to_items_dict(rows)
            # デフォルト品目を補完
            for k, v in DEFAULT_ITEMS.items():
                if k not in result:
                    result[k] = v
            return result
    # JSON フォールバック
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
    """品目名バリアントを保存。Sheets 接続時は別表記列を更新。"""
    if _sheets_available():
        current_sheets = _sc.load_master(force=True)
        for row in current_sheets:
            item = (row.get("品目") or "").strip()
            if item in items:
                variants = items[item]
                alt_names = [v for v in variants if v != item]
                row["別表記"] = ",".join(alt_names)
        # items dict にあるが Sheets にない品目を追加
        existing_items = {(r.get("品目") or "").strip() for r in current_sheets}
        for item_name, variants in items.items():
            if item_name not in existing_items:
                alt_names = [v for v in variants if v != item_name]
                current_sheets.append({
                    "品目": item_name,
                    "規格": get_default_spec_for_item(item_name),
                    "別表記": ",".join(alt_names),
                    "入数": 0,
                    "単位": "袋",
                    "受信方法": "総数",
                    "最小出荷単位": 0,
                })
        _sc.save_master(current_sheets)
        return
    # JSON フォールバック
    ensure_config_dir()
    with open(ITEMS_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_item_variant(normalized_name: str, variant: str):
    """品目の別表記を追加。"""
    items = load_items()
    if normalized_name not in items:
        items[normalized_name] = []
    if variant not in items[normalized_name]:
        items[normalized_name].append(variant)
    save_items(items)


def add_new_item(normalized_name: str, variants: Optional[List[str]] = None):
    """新しい品目を追加。"""
    items = load_items()
    if normalized_name not in items:
        items[normalized_name] = variants or [normalized_name]
        save_items(items)
        return True
    return False


def remove_item(normalized_name: str) -> bool:
    """品目を削除。Sheets 接続時は Sheets の行も削除する。"""
    if _sheets_available():
        current_sheets = _sc.load_master(force=True)
        new_rows = [r for r in current_sheets if (r.get("品目") or "").strip() != normalized_name]
        if len(new_rows) < len(current_sheets):
            _sc.save_master(new_rows)
            return True
        return False
    # JSON フォールバック
    items = load_items()
    if normalized_name in items:
        del items[normalized_name]
        save_items(items)
        return True
    return False


def auto_learn_item(item_name: str) -> str:
    """AI解析結果の品目名をマスタと照合し、正規名を返す。未登録なら自動追加。"""
    items = load_items()
    item_name = item_name.strip()
    for normalized, variants in items.items():
        if item_name in variants or any(variant in item_name for variant in variants):
            return normalized
    if item_name:
        add_new_item(item_name, [item_name])
    return item_name


# ================================================================
# 品目設定（入数・単位・受信方法）
# ================================================================

def load_item_settings() -> Dict[str, Dict[str, Any]]:
    """品目ごとの設定を返す。Sheets 接続時は Sheets から導出。"""
    if _sheets_available():
        rows = _sc.load_master()
        if rows:
            settings = {}
            for r in rows:
                item = (r.get("品目") or "").strip()
                if not item:
                    continue
                settings[item] = {
                    "default_unit": r.get("入数", 0),
                    "unit_type": r.get("単位", "袋"),
                    "receive_as_boxes": r.get("受信方法", "総数") == "箱数",
                    "min_shipping_unit": r.get("最小出荷単位", 0),
                }
            # デフォルト補完
            for k, v in DEFAULT_ITEM_SETTINGS.items():
                if k not in settings:
                    settings[k] = v.copy()
            return settings
    # JSON フォールバック
    ensure_config_dir()
    if ITEM_SETTINGS_FILE.exists():
        try:
            with open(ITEM_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged = DEFAULT_ITEM_SETTINGS.copy()
                    merged.update(data)
                    for key in ["長ねぎバラ", "長ネギバラ"]:
                        if key in merged:
                            merged[key] = {**merged[key], "default_unit": 50, "unit_type": "本"}
                    if "長ネギ" in merged:
                        merged["長ネギ"] = {**merged["長ネギ"], "default_unit": 30, "unit_type": "本"}
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
    """品目設定を保存。Sheets 接続時は Sheets の設定列を更新。"""
    if _sheets_available():
        current_sheets = _sc.load_master(force=True)
        for row in current_sheets:
            item = (row.get("品目") or "").strip()
            if item in settings:
                s = settings[item]
                row["入数"] = s.get("default_unit", 0)
                row["単位"] = s.get("unit_type", "袋")
                row["受信方法"] = "箱数" if s.get("receive_as_boxes") else "総数"
                row["最小出荷単位"] = s.get("min_shipping_unit", 0)
        _sc.save_master(current_sheets)
        return
    # JSON フォールバック
    ensure_config_dir()
    with open(ITEM_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


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
    """品目設定を削除。Sheets 接続時は remove_item() で行ごと削除済みなので JSON のみ。"""
    if _sheets_available():
        return
    settings = load_item_settings()
    if item in settings:
        del settings[item]
        save_item_settings(settings)


# ================================================================
# 品目設定の検索（get_item_setting）
# ================================================================

def get_item_setting(item: str, spec: Optional[str] = None) -> Dict[str, Any]:
    """品目（と規格）に一致する設定を返す。"""
    spec_s = (spec or "").strip()
    item_s = (item or "").strip()
    rows = load_item_spec_master()

    # 完全一致検索
    for r in rows:
        if (r.get("品目") or "").strip() != item_s:
            continue
        r_spec = (r.get("規格") or "").strip()
        if r_spec == spec_s:
            return _extract_setting(r)

    # 品目+規格が分かれている場合: 複合名（胡瓜バラ等）の行を参照
    if spec_s:
        if item_s == "胡瓜" and spec_s in ("100本", "50本"):
            composite_item = "胡瓜バラ(100本)" if spec_s == "100本" else "胡瓜バラ(50本)"
            for r in rows:
                if (r.get("品目") or "").strip() != composite_item:
                    continue
                if (r.get("規格") or "").strip() == "バラ":
                    return _extract_setting(r)
        composite_item = ITEM_SPEC_COMPOSITE_LOOKUP.get((item_s, spec_s))
        if composite_item:
            for r in rows:
                if (r.get("品目") or "").strip() != composite_item:
                    continue
                r_spec = (r.get("規格") or "").strip()
                if r_spec == spec_s:
                    return _extract_setting(r)

    # 規格なしの行にフォールバック
    if spec_s != "":
        for r in rows:
            if (r.get("品目") or "").strip() == item_s and (r.get("規格") or "").strip() == "":
                return _extract_setting(r)

    settings = load_item_settings()
    if item in settings:
        s = settings[item].copy()
        s.setdefault("receive_as_boxes", False)
        s.setdefault("min_shipping_unit", 0)
        return s
    return {"default_unit": 0, "unit_type": "袋", "receive_as_boxes": False, "min_shipping_unit": 0}


def _extract_setting(r: Dict[str, Any]) -> Dict[str, Any]:
    """マスタ行から設定辞書を抽出する共通処理。"""
    return {
        "default_unit": int(r.get("default_unit", 0)) or 0,
        "unit_type": (r.get("unit_type") or "袋").strip() or "袋",
        "receive_as_boxes": bool(r.get("receive_as_boxes", False)),
        "min_shipping_unit": int(r.get("min_shipping_unit", 0)) or 0,
    }


# ================================================================
# 入数キャッシュ（JSON のまま）
# ================================================================

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
        ("胡瓜", ""): 30, ("胡瓜平箱", ""): 50, ("胡瓜バラ(100本)", ""): 100, ("胡瓜バラ(50本)", ""): 50,
        ("長ネギ", ""): 30, ("長ねぎバラ", ""): 50, ("春菊", ""): 30, ("青梗菜", ""): 20,
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


# ================================================================
# 規格名解析・有効入数
# ================================================================

def extract_unit_size_from_spec(spec_name: Optional[str]) -> int:
    """規格名に含まれる数値（入数）を正規表現で抽出する。"""
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
    """合計数量計算用の有効入数（unit_size）を返す。"""
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
    """品目（と規格）ごとの最小出荷単位。"""
    setting = get_item_setting(item, spec)
    return int(setting.get("min_shipping_unit", 0)) or 0


def get_default_spec_for_item(item_name: str) -> str:
    """品目名に対する規格の既定表示値。"""
    s = (item_name or "").strip()
    _defaults = {
        "胡瓜": "3本", "胡瓜平箱": "平箱", "胡瓜バラ(100本)": "バラ", "胡瓜バラ(50本)": "バラ",
        "長ネギ": "2本", "長ねぎ": "2本", "長ねぎバラ": "バラ", "長ネギバラ": "バラ",
        "春菊": "1束", "青梗菜": "2~3株", "チンゲン菜": "2~3株",
    }
    return _defaults.get(s, "")


def get_known_specs_for_item(item: str) -> List[str]:
    """品目に対するマスタ登録済み規格のリスト。"""
    rows = load_item_spec_master()
    return [(r.get("規格") or "").strip() for r in rows if (r.get("品目") or "").strip() == (item or "").strip()]


def is_spec_in_master(item: str, spec: str) -> bool:
    """AI解析結果の規格がマスタに登録されているか。"""
    spec_s = (spec or "").strip()
    known = get_known_specs_for_item(item)
    if not known:
        return False
    return spec_s in known
