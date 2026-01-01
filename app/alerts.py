"""
Alert generation and management system.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional, List
from sqlalchemy.orm import Session

from database import AlertModel, WindowModel
from config import get_admin_config, get_public_config


def check_and_create_alerts(window: WindowModel, db: Session) -> List[AlertModel]:
    """
    Check a window for alert conditions and create alerts if needed.
    Returns list of created alerts.
    """
    created_alerts = []
    admin_config = get_admin_config()
    public_config = get_public_config()
    
    # Check if alerts are enabled
    if not public_config.alerts.get("enable_public_alerts", True):
        return created_alerts
    
    total_flows = window.total_flows
    if total_flows == 0:
        return created_alerts
    
    attack_percent = (window.attack_flows / total_flows * 100) if total_flows > 0 else 0.0
    unknown_percent = (window.unknown_flows / total_flows * 100) if total_flows > 0 else 0.0
    
    threshold_attack = public_config.alerts.get("alert_threshold_attack_percent", 10.0)
    threshold_unknown = public_config.alerts.get("alert_threshold_unknown_percent", 20.0)
    threshold_flows = public_config.alerts.get("alert_threshold_flow_count", 1000)
    
    # Critical alert: Very high attack percentage
    if attack_percent >= 50:
        alert = AlertModel(
            window_id=window.id,
            alert_type="critical",
            severity="high",
            title="Critical: High Attack Rate Detected",
            message=f"Window {window.id} shows {attack_percent:.1f}% attack flows ({window.attack_flows} out of {total_flows} flows). Immediate attention required.",
            alert_metadata={
                "attack_percent": attack_percent,
                "attack_flows": window.attack_flows,
                "total_flows": total_flows,
                "window_start": window.start_time.isoformat(),
            },
        )
        db.add(alert)
        created_alerts.append(alert)
    
    # Elevated alert: Moderate attack percentage
    elif attack_percent >= threshold_attack:
        alert = AlertModel(
            window_id=window.id,
            alert_type="elevated",
            severity="medium",
            title="Elevated: Attack Activity Detected",
            message=f"Window {window.id} shows {attack_percent:.1f}% attack flows ({window.attack_flows} out of {total_flows} flows). Review recommended.",
            alert_metadata={
                "attack_percent": attack_percent,
                "attack_flows": window.attack_flows,
                "total_flows": total_flows,
                "window_start": window.start_time.isoformat(),
            },
        )
        db.add(alert)
        created_alerts.append(alert)
    
    # Unknown flows alert
    if unknown_percent >= threshold_unknown:
        alert = AlertModel(
            window_id=window.id,
            alert_type="elevated",
            severity="medium",
            title="Elevated: High Unknown Flow Rate",
            message=f"Window {window.id} shows {unknown_percent:.1f}% unknown flows ({window.unknown_flows} out of {total_flows} flows). Investigation recommended.",
            alert_metadata={
                "unknown_percent": unknown_percent,
                "unknown_flows": window.unknown_flows,
                "total_flows": total_flows,
                "window_start": window.start_time.isoformat(),
            },
        )
        db.add(alert)
        created_alerts.append(alert)
    
    # High flow volume alert
    if total_flows >= threshold_flows:
        alert = AlertModel(
            window_id=window.id,
            alert_type="info",
            severity="low",
            title="Info: High Traffic Volume",
            message=f"Window {window.id} shows high traffic volume: {total_flows} flows. This may indicate increased activity or potential DDoS.",
            alert_metadata={
                "total_flows": total_flows,
                "window_start": window.start_time.isoformat(),
            },
        )
        db.add(alert)
        created_alerts.append(alert)
    
    # Check for specific attack types
    if window.attacks_per_label:
        for attack_label, count in window.attacks_per_label.items():
            if count >= 10:  # Threshold for specific attack type
                alert = AlertModel(
                    window_id=window.id,
                    alert_type="elevated",
                    severity="medium",
                    title=f"Elevated: {attack_label} Activity",
                    message=f"Window {window.id} detected {count} flows classified as '{attack_label}'. Review recommended.",
                    alert_metadata={
                        "attack_label": attack_label,
                        "count": count,
                        "window_start": window.start_time.isoformat(),
                    },
                )
                db.add(alert)
                created_alerts.append(alert)
    
    if created_alerts:
        db.commit()
    
    return created_alerts


def get_unacknowledged_alerts_count(db: Session) -> int:
    """Get count of unacknowledged alerts."""
    return db.query(AlertModel).filter(
        AlertModel.acknowledged == False,
        AlertModel.resolved == False,
    ).count()


def get_critical_alerts_count(db: Session) -> int:
    """Get count of critical alerts."""
    return db.query(AlertModel).filter(
        AlertModel.alert_type == "critical",
        AlertModel.resolved == False,
    ).count()

