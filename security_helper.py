from pathlib import Path
import json
import os
import platform
import hashlib
import base64
from cryptography.fernet import Fernet, InvalidToken

CONFIG_FILE = Path("config.json")

# --- Machine-specific key derivation (from crypto_utils.py) ---
APP_SALT = b"llm_eval_v1_salt"

def _machine_secret() -> bytes:
    raw = f"{platform.node()}:{os.getenv('USER', os.getenv('USERNAME', 'llm_eval'))}"
    return hashlib.sha256(raw.encode()).digest()

def get_cipher():
    secret = _machine_secret()
    key_material = hashlib.pbkdf2_hmac(
        "sha256", secret, APP_SALT, iterations=100_000, dklen=32
    )
    fernet_key = base64.urlsafe_b64encode(key_material)
    return Fernet(fernet_key)

# --- Configuration Management ---
DEFAULT_CONFIG = {
    "OPENAI_API_KEYS": [],
    "GOOGLE_API_KEYS": [],
    "ANTHROPIC_API_KEYS": [],
    "GROQ_API_KEYS": [],
    "selected_model": "groq",
    "weights": {
        "accuracy": 20,
        "relevance": 15,
        "completeness": 15,
        "consistency": 10,
        "usefulness": 10,
        "structure": 10,
        "conciseness": 10,
        "latency": 5,
        "cost": 5,
    },
}

def deep_copy_default():
    return json.loads(json.dumps(DEFAULT_CONFIG))

def load_config():
    if not CONFIG_FILE.exists():
        return deep_copy_default()
    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8").strip()
        if not raw:
            return deep_copy_default()
        data = json.loads(raw)
        config = deep_copy_default()
        for key in ["OPENAI_API_KEYS", "GOOGLE_API_KEYS", "ANTHROPIC_API_KEYS", "GROQ_API_KEYS"]:
            if key in data and isinstance(data[key], list):
                config[key] = data[key]
        config.update({k: v for k, v in data.items() if "API_KEYS" not in k and k != "weights"})
        if isinstance(data.get("weights"), dict):
            config["weights"].update(data["weights"])
        return config
    except Exception:
        return deep_copy_default()

def save_config(config):
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

# --- Secret Management ---
def encrypt_secret(plain_text: str) -> str:
    if not plain_text:
        return ""
    return get_cipher().encrypt(plain_text.encode()).decode()

def decrypt_secret(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    try:
        return get_cipher().decrypt(cipher_text.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Unable to decrypt API key: data may be corrupt or from a different machine.")

def safe_decrypt_secret(value: str) -> str:
    if not value:
        return ""
    try:
        return decrypt_secret(value)
    except Exception:
        return value

def store_api_key(config: dict, provider: str, api_key: str):
    field_map = {
        "openai": "OPENAI_API_KEYS",
        "google": "GOOGLE_API_KEYS",
        "anthropic": "ANTHROPIC_API_KEYS",
        "groq": "GROQ_API_KEYS",
    }
    key_name = field_map[provider]
    if api_key.strip():
        encrypted_key = encrypt_secret(api_key)
        if encrypted_key not in config[key_name]:
            config[key_name].append(encrypted_key)

def get_api_key(provider: str) -> str:
    config = load_config()
    field_map = {
        "openai": "OPENAI_API_KEYS",
        "google": "GOOGLE_API_KEYS",
        "anthropic": "ANTHROPIC_API_KEYS",
        "groq": "GROQ_API_KEYS",
    }
    key_name = field_map[provider]
    if config.get(key_name):
        return decrypt_secret(config[key_name][-1])
    return ""