"""
User Authentication Module
JSON-based user storage with bcrypt password hashing and session management.
"""

from __future__ import annotations

import json
import uuid
import hashlib
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from security_helper import encrypt_secret, safe_decrypt_secret

# File paths
USERS_FILE = Path("users.json")
SESSIONS_FILE = Path("sessions.json")
USER_DATA_DIR = Path("user_data")

# Session expiry (24 hours)
SESSION_EXPIRY_HOURS = 24


def _hash_password(password: str) -> str:
    """Hash password using SHA-256 with salt (simple alternative to bcrypt)."""
    salt = "llm_eval_auth_salt_v1"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    return _hash_password(password) == password_hash


def _load_users() -> Dict[str, Any]:
    """Load users from JSON file."""
    if not USERS_FILE.exists():
        return {"users": {}}
    try:
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        return data if "users" in data else {"users": {}}
    except Exception:
        return {"users": {}}


def _save_users(data: Dict[str, Any]):
    """Save users to JSON file."""
    USERS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_sessions() -> Dict[str, Any]:
    """Load sessions from JSON file."""
    if not SESSIONS_FILE.exists():
        return {}
    try:
        return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sessions(data: Dict[str, Any]):
    """Save sessions to JSON file."""
    SESSIONS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _get_user_data_dir(user_id: str) -> Path:
    """Get the data directory for a specific user."""
    user_dir = USER_DATA_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def create_user(username: str, email: str, password: str) -> tuple[bool, str]:
    """
    Create a new user account.
    Returns (success, message/user_id).
    """
    data = _load_users()
    
    # Check for existing username or email
    for uid, user in data["users"].items():
        if user["username"].lower() == username.lower():
            return False, "Username already exists"
        if user["email"].lower() == email.lower():
            return False, "Email already registered"
    
    # Create new user
    user_id = str(uuid.uuid4())[:8]
    data["users"][user_id] = {
        "username": username,
        "email": email,
        "password_hash": _hash_password(password),
        "created_at": datetime.now().isoformat(),
        "api_keys": {
            "openai": [],
            "groq": [],
            "google": [],
            "anthropic": []
        },
        "config": {
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
            }
        },
        "stats": {
            "total_evaluations": 0,
            "last_evaluation": None,
            "evaluations_by_type": {"dataset": 0, "file": 0},
            "model_usage": {}
        }
    }
    
    _save_users(data)
    
    # Create user data directory
    _get_user_data_dir(user_id)
    
    # Create empty history file
    history_file = _get_user_data_dir(user_id) / "history.json"
    history_file.write_text("[]", encoding="utf-8")
    
    return True, user_id


def authenticate_user(username: str, password: str) -> tuple[bool, Optional[str]]:
    """
    Authenticate user with username/email and password.
    Returns (success, user_id or None).
    """
    data = _load_users()
    
    for uid, user in data["users"].items():
        if (user["username"].lower() == username.lower() or 
            user["email"].lower() == username.lower()):
            if _verify_password(password, user["password_hash"]):
                return True, uid
            return False, None
    
    return False, None


def create_session(user_id: str) -> str:
    """Create a new session for user and return session token."""
    sessions = _load_sessions()
    
    # Clean expired sessions
    now = time.time()
    sessions = {
        tok: sess for tok, sess in sessions.items()
        if sess["expires_at"] > now
    }
    
    # Create new session
    token = str(uuid.uuid4())
    sessions[token] = {
        "user_id": user_id,
        "created_at": now,
        "expires_at": now + (SESSION_EXPIRY_HOURS * 3600)
    }
    
    _save_sessions(sessions)
    return token


def validate_session(token: str) -> Optional[str]:
    """
    Validate session token.
    Returns user_id if valid, None otherwise.
    """
    if not token:
        return None
    
    sessions = _load_sessions()
    session = sessions.get(token)
    
    if not session:
        return None
    
    if session["expires_at"] < time.time():
        # Session expired, clean up
        del sessions[token]
        _save_sessions(sessions)
        return None
    
    return session["user_id"]


def destroy_session(token: str):
    """Destroy a session (logout)."""
    sessions = _load_sessions()
    if token in sessions:
        del sessions[token]
        _save_sessions(sessions)


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user data by ID."""
    data = _load_users()
    user = data["users"].get(user_id)
    if user:
        user["id"] = user_id
    return user


def update_user_api_keys(user_id: str, provider: str, api_key: str):
    """Add an API key for a user (encrypted)."""
    data = _load_users()
    if user_id not in data["users"]:
        return False
    
    if api_key.strip():
        encrypted = encrypt_secret(api_key)
        if encrypted not in data["users"][user_id]["api_keys"].get(provider, []):
            if provider not in data["users"][user_id]["api_keys"]:
                data["users"][user_id]["api_keys"][provider] = []
            data["users"][user_id]["api_keys"][provider].append(encrypted)
            _save_users(data)
    
    return True


def get_user_api_key(user_id: str, provider: str) -> str:
    """Get the latest API key for a user and provider (decrypted)."""
    user = get_user(user_id)
    if not user:
        return ""
    
    keys = user.get("api_keys", {}).get(provider, [])
    if keys:
        return safe_decrypt_secret(keys[-1])
    return ""


def update_user_config(user_id: str, config: Dict[str, Any]):
    """Update user configuration (model selection, weights)."""
    data = _load_users()
    if user_id not in data["users"]:
        return False
    
    data["users"][user_id]["config"].update(config)
    _save_users(data)
    return True


def get_user_config(user_id: str) -> Dict[str, Any]:
    """Get user configuration."""
    user = get_user(user_id)
    if not user:
        return {}
    return user.get("config", {})


def add_evaluation_history(
    user_id: str,
    eval_type: str,
    filename: str = "",
    results_summary: Dict[str, Any] = None
):
    """Add an evaluation to user's history."""
    history_file = _get_user_data_dir(user_id) / "history.json"
    
    try:
        history = json.loads(history_file.read_text(encoding="utf-8"))
    except Exception:
        history = []
    
    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now().isoformat(),
        "type": eval_type,
        "filename": filename,
        "results_summary": results_summary or {}
    }
    
    history.insert(0, entry)  # Most recent first
    history = history[:100]   # Keep last 100 entries
    
    history_file.write_text(json.dumps(history, indent=2), encoding="utf-8")
    
    # Update stats
    data = _load_users()
    if user_id in data["users"]:
        stats = data["users"][user_id].get("stats", {})
        stats["total_evaluations"] = stats.get("total_evaluations", 0) + 1
        stats["last_evaluation"] = datetime.now().isoformat()
        
        by_type = stats.get("evaluations_by_type", {"dataset": 0, "file": 0})
        by_type[eval_type] = by_type.get(eval_type, 0) + 1
        stats["evaluations_by_type"] = by_type
        
        # Track model usage
        model = data["users"][user_id].get("config", {}).get("selected_model", "unknown")
        model_usage = stats.get("model_usage", {})
        model_usage[model] = model_usage.get(model, 0) + 1
        stats["model_usage"] = model_usage
        
        data["users"][user_id]["stats"] = stats
        _save_users(data)
    
    return entry["id"]


def get_evaluation_history(user_id: str, limit: int = 50) -> list:
    """Get user's evaluation history."""
    history_file = _get_user_data_dir(user_id) / "history.json"
    
    try:
        history = json.loads(history_file.read_text(encoding="utf-8"))
        return history[:limit]
    except Exception:
        return []


def get_user_stats(user_id: str) -> Dict[str, Any]:
    """Get user statistics."""
    user = get_user(user_id)
    if not user:
        return {}
    
    stats = user.get("stats", {})
    history = get_evaluation_history(user_id)
    
    # Calculate additional stats from history
    if history:
        scores = []
        for entry in history:
            summary = entry.get("results_summary", {})
            if "avg_score" in summary:
                scores.append(summary["avg_score"])
        
        if scores:
            stats["average_score"] = round(sum(scores) / len(scores), 2)
            stats["highest_score"] = round(max(scores), 2)
            stats["lowest_score"] = round(min(scores), 2)
    
    # Count configured API keys
    api_keys = user.get("api_keys", {})
    stats["configured_providers"] = sum(1 for keys in api_keys.values() if keys)
    
    return stats


def clear_user_api_keys(user_id: str, provider: str):
    """Clear all API keys for a provider."""
    data = _load_users()
    if user_id in data["users"]:
        data["users"][user_id]["api_keys"][provider] = []
        _save_users(data)
