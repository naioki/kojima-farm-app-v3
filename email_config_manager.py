"""
メール設定管理モジュール
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict

CONFIG_DIR = Path("config")
EMAIL_CONFIG_FILE = CONFIG_DIR / "email_config.json"

IMAP_SERVER_MAP = {
    "gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com",
    "outlook.com": "outlook.office365.com", "hotmail.com": "outlook.office365.com",
    "live.com": "outlook.office365.com", "yahoo.co.jp": "imap.mail.yahoo.com",
    "yahoo.com": "imap.mail.yahoo.com", "icloud.com": "imap.mail.me.com",
    "me.com": "imap.mail.me.com", "aol.com": "imap.aol.com"
}

def detect_imap_server(email_address: str) -> str:
    if not email_address:
        return "imap.gmail.com"
    domain = email_address.split("@")[-1].lower() if "@" in email_address else ""
    if domain in IMAP_SERVER_MAP:
        return IMAP_SERVER_MAP[domain]
    for key, server in IMAP_SERVER_MAP.items():
        if key in domain:
            return server
    return "imap.gmail.com"

def ensure_config_dir():
    CONFIG_DIR.mkdir(exist_ok=True)

def _get_secrets_password(st_secrets) -> str:
    """Secretsからパスワードを取得（ファイル保存とは独立）"""
    if st_secrets is None:
        return ""
    try:
        secrets = st_secrets.get("email", {})
        return secrets.get("email_password", "") if secrets else ""
    except Exception:
        return ""


def load_email_config(st_secrets=None) -> Dict:
    """保存済み設定を返す。ファイル保存を優先し、パスワードは常にSecretsから補完。"""
    ensure_config_dir()
    secrets_pw = _get_secrets_password(st_secrets)

    if EMAIL_CONFIG_FILE.exists():
        try:
            with open(EMAIL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                if config.get("email_address"):
                    return {
                        "imap_server": config.get("imap_server", ""),
                        "email_address": config.get("email_address", ""),
                        "email_password": secrets_pw,
                        "sender_email": config.get("sender_email", ""),
                        "days_back": config.get("days_back", 1),
                    }
        except Exception:
            pass
    if st_secrets is not None:
        try:
            secrets = st_secrets.get("email", {})
            if secrets and secrets.get("email_address"):
                return {
                    "imap_server": secrets.get("imap_server", ""),
                    "email_address": secrets.get("email_address", ""),
                    "email_password": secrets_pw,
                    "sender_email": secrets.get("sender_email", ""),
                    "days_back": secrets.get("days_back", 1),
                }
        except Exception:
            pass
    return {"imap_server": "", "email_address": "", "email_password": "", "sender_email": "", "days_back": 1}

def save_email_config(imap_server: str, email_address: str, sender_email: str, days_back: int, save_to_file: bool = False):
    if not save_to_file:
        return
    ensure_config_dir()
    config = {"imap_server": imap_server, "email_address": email_address, "sender_email": sender_email, "days_back": days_back}
    with open(EMAIL_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

SENDER_RULES_FILE = CONFIG_DIR / "sender_rules.json"

def load_sender_rules() -> Dict[str, Dict]:
    ensure_config_dir()
    if SENDER_RULES_FILE.exists():
        try:
            with open(SENDER_RULES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_sender_rules(rules: Dict[str, Dict]):
    ensure_config_dir()
    with open(SENDER_RULES_FILE, 'w', encoding='utf-8') as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

def get_sender_rule(sender: str) -> Optional[Dict]:
    rules = load_sender_rules()
    if not sender:
        return None
    # Exact match first
    if sender in rules:
        return rules[sender]
    # Domain match? (Not implemented for now, maybe later)
    return None
