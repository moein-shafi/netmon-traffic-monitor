"""
Configuration management for NetMon.
Supports both public and admin-only settings.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict, field
from datetime import timedelta

CONFIG_DIR = Path("/var/netmon/config")
PUBLIC_CONFIG_PATH = CONFIG_DIR / "public_config.json"
ADMIN_CONFIG_PATH = CONFIG_DIR / "admin_config.json"
SECRETS_PATH = CONFIG_DIR / ".secrets.json"

# Default public configuration (visible to all users)
DEFAULT_PUBLIC_CONFIG = {
    "dashboard": {
        "refresh_interval_seconds": 60,
        "max_windows_display": 12,
        "timezone": "UTC",
        "theme": "dark",
        "chart_animation": True,
        "auto_refresh": True,
    },
    "display": {
        "show_attack_details": True,
        "show_llm_summaries": True,
        "show_feature_stats": True,
        "show_risk_indicators": True,
        "compact_mode": False,
    },
    "alerts": {
        "enable_public_alerts": True,
        "alert_threshold_attack_percent": 10.0,
        "alert_threshold_unknown_percent": 20.0,
        "alert_threshold_flow_count": 1000,
    },
}

# Default admin configuration (only accessible to admins)
DEFAULT_ADMIN_CONFIG = {
    "capture": {
        "pcap_dir": "/var/pcaps",
        "csv_dir": "/var/netmon/flows",
        "window_duration_minutes": 5,
        "max_windows_keep": 12,
        "worker_interval_seconds": 60,
        "pcap_min_age_seconds": 10,
    },
    "ml": {
        "model_path": "/opt/netmon/model/netmon_rf.joblib",
        "threshold": 0.90,
        "enabled": True,
    },
    "llm": {
        "ollama_url": "http://127.0.0.1:11434/api/generate",
        "ollama_model": "smollm2:135m",
        "enabled": True,
        "timeout_seconds": 60,
    },
    "ntlflowlyzer": {
        "binary_path": "/opt/netmon/env/bin/ntlflowlyzer",
        "threads": 4,
        "min_flows": 1,
        "min_rows": 1,
        "max_rows": 800000,
        "max_retries": 3,
        "retry_delay_seconds": 5,
        "parallel_processing": False,
        "batch_size": 10,
    },
    "security": {
        "session_timeout_minutes": 60,
        "max_login_attempts": 5,
        "lockout_duration_minutes": 15,
        "require_https": False,
        "allowed_origins": ["*"],
    },
    "storage": {
        "windows_path": "/var/netmon/windows.json",
        "backup_enabled": True,
        "backup_interval_hours": 24,
        "retention_days": 7,
    },
    "notifications": {
        "email_enabled": False,
        "webhook_enabled": False,
        "webhook_url": "",
        "alert_on_critical": True,
        "alert_on_elevated": False,
    },
}


@dataclass
class PublicConfig:
    """Public configuration that all users can view and modify (within limits)."""
    dashboard: Dict[str, Any] = field(default_factory=lambda: DEFAULT_PUBLIC_CONFIG["dashboard"].copy())
    display: Dict[str, Any] = field(default_factory=lambda: DEFAULT_PUBLIC_CONFIG["display"].copy())
    alerts: Dict[str, Any] = field(default_factory=lambda: DEFAULT_PUBLIC_CONFIG["alerts"].copy())

    @classmethod
    def load(cls) -> PublicConfig:
        """Load public configuration from disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not PUBLIC_CONFIG_PATH.exists():
            config = cls()
            config.save()
            return config
        
        try:
            with PUBLIC_CONFIG_PATH.open("r") as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            print(f"[config] Failed to load public config: {e}, using defaults")
            return cls()

    def save(self) -> None:
        """Save public configuration to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with PUBLIC_CONFIG_PATH.open("w") as f:
            json.dump(asdict(self), f, indent=2)

    def update(self, updates: Dict[str, Any]) -> None:
        """Update configuration with new values."""
        for key, value in updates.items():
            if hasattr(self, key) and isinstance(getattr(self, key), dict):
                getattr(self, key).update(value)
            else:
                setattr(self, key, value)
        self.save()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AdminConfig:
    """Admin-only configuration."""
    capture: Dict[str, Any] = field(default_factory=lambda: DEFAULT_ADMIN_CONFIG["capture"].copy())
    ml: Dict[str, Any] = field(default_factory=lambda: DEFAULT_ADMIN_CONFIG["ml"].copy())
    llm: Dict[str, Any] = field(default_factory=lambda: DEFAULT_ADMIN_CONFIG["llm"].copy())
    ntlflowlyzer: Dict[str, Any] = field(default_factory=lambda: DEFAULT_ADMIN_CONFIG["ntlflowlyzer"].copy())
    security: Dict[str, Any] = field(default_factory=lambda: DEFAULT_ADMIN_CONFIG["security"].copy())
    storage: Dict[str, Any] = field(default_factory=lambda: DEFAULT_ADMIN_CONFIG["storage"].copy())
    notifications: Dict[str, Any] = field(default_factory=lambda: DEFAULT_ADMIN_CONFIG["notifications"].copy())

    @classmethod
    def load(cls) -> AdminConfig:
        """Load admin configuration from disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not ADMIN_CONFIG_PATH.exists():
            config = cls()
            config.save()
            return config
        
        try:
            with ADMIN_CONFIG_PATH.open("r") as f:
                data = json.load(f)
            return cls(**data)
        except Exception as e:
            print(f"[config] Failed to load admin config: {e}, using defaults")
            return cls()

    def save(self) -> None:
        """Save admin configuration to disk."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with ADMIN_CONFIG_PATH.open("w") as f:
            json.dump(asdict(self), f, indent=2)

    def update(self, updates: Dict[str, Any]) -> None:
        """Update configuration with new values."""
        for key, value in updates.items():
            if hasattr(self, key) and isinstance(getattr(self, key), dict):
                getattr(self, key).update(value)
            else:
                setattr(self, key, value)
        self.save()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def get_public_config() -> PublicConfig:
    """Get the current public configuration."""
    return PublicConfig.load()


def get_admin_config() -> AdminConfig:
    """Get the current admin configuration."""
    return AdminConfig.load()

