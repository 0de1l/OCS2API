# -*- coding: utf-8 -*-
"""Runtime configuration for source and PyInstaller builds."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict


IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
# Containers mount the whole data directory so atomic file replacement works.
DATA_DIR = APP_DIR if IS_FROZEN else Path(os.getenv("OCS2API_DATA_DIR") or APP_DIR).resolve()
CONFIG_PATH = DATA_DIR / "config.json"
QUESTION_BANK_PATH = DATA_DIR / "question_bank.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "host": "0.0.0.0",
    "port": 5000,
    "openai_api_base": "https://api.openai.com/v1",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "access_token": "",
    "log_level": "INFO",
    "max_tokens": 500,
    "temperature": 0.7,
    "enable_cache": True,
    "cache_expiration": 86400,
}


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            value = json.load(file)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"无法读取配置文件 {path}: {exc}") from exc


def _source_environment() -> Dict[str, Any]:
    """Keep .env support for development, but never load it from a frozen exe."""
    if IS_FROZEN:
        return {}

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=APP_DIR / ".env", override=True)
    values: Dict[str, Any] = {}
    mapping = {
        "HOST": "host",
        "PORT": "port",
        "OPENAI_API_BASE": "openai_api_base",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
        "ACCESS_TOKEN": "access_token",
        "LOG_LEVEL": "log_level",
        "MAX_TOKENS": "max_tokens",
        "TEMPERATURE": "temperature",
        "ENABLE_CACHE": "enable_cache",
        "CACHE_EXPIRATION": "cache_expiration",
    }
    for env_name, setting_name in mapping.items():
        value = os.getenv(env_name)
        if value is not None:
            values[setting_name] = value
    return values


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    settings = {**DEFAULT_SETTINGS, **values}
    try:
        port = int(settings["port"])
        max_tokens = int(settings["max_tokens"])
        temperature = float(settings["temperature"])
        cache_expiration = int(settings["cache_expiration"])
    except (TypeError, ValueError) as exc:
        raise ValueError("端口、最大 Token 数、温度和缓存时长必须是有效数字") from exc

    if not 1 <= port <= 65535:
        raise ValueError("端口必须在 1 到 65535 之间")
    if max_tokens < 1:
        raise ValueError("最大 Token 数必须大于 0")
    if not 0 <= temperature <= 2:
        raise ValueError("温度必须在 0 到 2 之间")
    if cache_expiration < 1:
        raise ValueError("缓存时长必须大于 0")

    settings.update(
        {
            "host": str(settings["host"]).strip() or "0.0.0.0",
            "port": port,
            "openai_api_base": str(settings["openai_api_base"]).strip().rstrip("/"),
            "openai_api_key": str(settings.get("openai_api_key") or "").strip(),
            "openai_model": str(settings["openai_model"]).strip() or DEFAULT_SETTINGS["openai_model"],
            "access_token": str(settings.get("access_token") or "").strip(),
            "log_level": str(settings.get("log_level") or "INFO").strip().upper(),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "enable_cache": _as_bool(settings["enable_cache"]),
            "cache_expiration": cache_expiration,
        }
    )
    if not settings["openai_api_base"]:
        raise ValueError("上游模型 URL 不能为空")
    return settings


def load_settings() -> Dict[str, Any]:
    """Load defaults, development environment values, and persisted UI values."""
    values = {**DEFAULT_SETTINGS, **_source_environment()}
    if CONFIG_PATH.exists():
        values.update(_read_json(CONFIG_PATH))
    return normalize_settings(values)


def save_settings(settings: Dict[str, Any]) -> None:
    """Atomically persist settings next to the executable."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_path = tempfile.mkstemp(
        prefix="config.", suffix=".tmp", dir=str(CONFIG_PATH.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(payload)
        os.replace(temporary_path, CONFIG_PATH)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


class Config:
    """Compatibility facade for the existing service code."""

    _settings: Dict[str, Any] = {}

    @classmethod
    def reload(cls) -> None:
        cls._settings = load_settings()
        for key, value in cls._settings.items():
            setattr(cls, key.upper(), value)

    @classmethod
    def update(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        current = dict(cls._settings)
        allowed = {
            "host",
            "port",
            "openai_api_base",
            "openai_model",
            "log_level",
            "max_tokens",
            "temperature",
            "enable_cache",
            "cache_expiration",
        }
        for key in allowed:
            if key in payload:
                current[key] = payload[key]

        if payload.get("clear_api_key"):
            current["openai_api_key"] = ""
        elif payload.get("openai_api_key"):
            current["openai_api_key"] = payload["openai_api_key"]

        if payload.get("clear_access_token"):
            current["access_token"] = ""
        elif "access_token" in payload and payload["access_token"]:
            current["access_token"] = payload["access_token"]

        normalized = normalize_settings(current)
        save_settings(normalized)
        cls._settings = normalized
        for key, value in normalized.items():
            setattr(cls, key.upper(), value)
        return normalized

    @classmethod
    def public(cls) -> Dict[str, Any]:
        return {
            "host": cls.HOST,
            "port": cls.PORT,
            "openai_api_base": cls.OPENAI_API_BASE,
            "openai_model": cls.OPENAI_MODEL,
            "max_tokens": cls.MAX_TOKENS,
            "temperature": cls.TEMPERATURE,
            "enable_cache": cls.ENABLE_CACHE,
            "cache_expiration": cls.CACHE_EXPIRATION,
            "api_key_configured": bool(cls.OPENAI_API_KEY),
            "api_key_masked": ("••••" + cls.OPENAI_API_KEY[-4:]) if cls.OPENAI_API_KEY else "",
            "access_token_enabled": bool(cls.ACCESS_TOKEN),
            "config_path": str(CONFIG_PATH),
            "question_bank_path": str(QUESTION_BANK_PATH),
        }

    @classmethod
    def api_key(cls) -> str:
        return cls.OPENAI_API_KEY


Config.reload()

if IS_FROZEN and not CONFIG_PATH.exists():
    save_settings(Config._settings)
