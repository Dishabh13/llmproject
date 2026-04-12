"""
crypto_utils.py
===============
Lightweight encryption helpers for storing API keys in config.json.

We use Fernet (AES-128-CBC + HMAC-SHA256) from the `cryptography` package.
If that package is not installed we fall back to base64 obfuscation with a
warning so the app still works on minimal installs.

The encryption key is derived from a machine-specific secret and a fixed
application salt so config.json is not portable across machines (acceptable
for a local dev tool).
"""

from __future__ import annotations

import base64
import hashlib
import os
import platform
import warnings

# ── derive a stable machine secret ──────────────────────────────────────────

def _machine_secret() -> bytes:
    """
    Produce a ~32-byte secret that is stable for this user on this machine.
    We combine the hostname and username as a simple machine-bound value.
    """
    raw = f"{platform.node()}:{os.getenv('USER', os.getenv('USERNAME', 'llm_eval'))}"
    return hashlib.sha256(raw.encode()).digest()

APP_SALT = b"llm_eval_v1_salt"   # fixed app-level salt

# ── try to import Fernet ─────────────────────────────────────────────────────

try:
    from cryptography.fernet import Fernet
    import base64 as _b64

    def _fernet() -> "Fernet":
        secret = _machine_secret()
        key_material = hashlib.pbkdf2_hmac(
            "sha256", secret, APP_SALT, iterations=100_000, dklen=32
        )
        fernet_key = _b64.urlsafe_b64encode(key_material)
        return Fernet(fernet_key)

    def encrypt_value(plaintext: str) -> str:
        """Return a Fernet-encrypted, base64-encoded string prefixed with 'enc:'."""
        if not plaintext:
            return plaintext
        token = _fernet().encrypt(plaintext.encode()).decode()
        return f"enc:{token}"

    def decrypt_value(value: str) -> str:
        """Decrypt a value previously produced by encrypt_value."""
        if not value or not value.startswith("enc:"):
            return value
        token = value[4:].encode()
        return _fernet().decrypt(token).decode()

    ENCRYPTION_AVAILABLE = True

except ImportError:
    warnings.warn(
        "The 'cryptography' package is not installed. "
        "API keys will be obfuscated with base64 only (not encrypted). "
        "Install it with:  pip install cryptography",
        stacklevel=2,
    )

    def encrypt_value(plaintext: str) -> str:      # type: ignore[misc]
        if not plaintext:
            return plaintext
        return "b64:" + base64.b64encode(plaintext.encode()).decode()

    def decrypt_value(value: str) -> str:          # type: ignore[misc]
        if not value:
            return value
        if value.startswith("b64:"):
            return base64.b64decode(value[4:]).decode()
        if value.startswith("enc:"):
            # was encrypted on a machine that had cryptography; can't decrypt
            return ""
        return value

    ENCRYPTION_AVAILABLE = False


# ── helpers for config dicts ─────────────────────────────────────────────────

_KEY_FIELDS = ("OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "GROQ_API_KEY")


def encrypt_config_keys(config: dict) -> dict:
    """Return a new config dict with API key fields encrypted."""
    out = dict(config)
    for field in _KEY_FIELDS:
        if field in out and out[field] and not str(out[field]).startswith(("enc:", "b64:")):
            out[field] = encrypt_value(out[field])
    return out


def decrypt_config_keys(config: dict) -> dict:
    """Return a new config dict with API key fields decrypted."""
    out = dict(config)
    for field in _KEY_FIELDS:
        if field in out:
            out[field] = decrypt_value(out[field])
    return out
