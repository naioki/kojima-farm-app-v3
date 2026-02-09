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

def load_email_config(st_secrets=None) -> Dict:
    if st_secrets is not None:
        try:
            secrets = st_secrets.get("email", {})
            if secrets and secrets.get("email_address"):
                return {
                    "imap_server": secrets.get("imap_server", ""),
                    "email_address": secrets.get("email_address", ""),
                    "sender_email": secrets.get("sender_email", ""),
                    "days_back": secrets.get("days_back", 1)
                }
        except Exception:
            pass
    ensure_config_dir()
    if EMAIL_CONFIG_FILE.exists():
        try:
            with open(EMAIL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return {
                    "imap_server": config.get("imap_server", ""),
                    "email_address": config.get("email_address", ""),
                    "sender_email": config.get("sender_email", ""),
                    "days_back": config.get("days_back", 1)
                }
        except Exception:
            pass
    return {"imap_server": "", "email_address": "", "sender_email": "", "days_back": 1}

def save_email_config(imap_server: str, email_address: str, sender_email: str, days_back: int, save_to_file: bool = False):
    if not save_to_file:
        return
    ensure_config_dir()
    config = {"imap_server": imap_server, "email_address": email_address, "sender_email": sender_email, "days_back": days_back}
    with open(EMAIL_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
