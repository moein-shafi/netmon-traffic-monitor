"""
Enhanced NetMon API with authentication, configuration, alerts, and analytics.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Depends, Request, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.storage import load_windows, Window, save_windows
from app.auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    require_admin,
    create_user,
    update_user_password,
    list_users,
    security,
)
from app.config import get_public_config, get_admin_config, PublicConfig, AdminConfig
from app.database import (
    get_db,
    WindowModel,
    AlertModel,
    AuditLogModel,
    init_db,
)

# Initialize database
init_db()

app = FastAPI(
    title="NetMon Traffic Monitor API",
    description="Professional network traffic monitoring with ML-based threat detection and LLM-powered analysis",
    version="2.0.0",
)

# CORS middleware (will be configurable via admin config)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Will be overridden by admin config
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for requests/responses
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    updates: Dict[str, Any]


class AlertAcknowledgeRequest(BaseModel):
    alert_id: int


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "user"


class PasswordUpdateRequest(BaseModel):
    current_password: str
    new_password: str


class AnalyticsRequest(BaseModel):
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    metric: str = "total_flows"


# ==================== Public Endpoints ====================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard."""
    index_path = Path("templates/index.html")
    if index_path.exists():
        return index_path.read_text()
    return "<h1>NetMon Traffic Monitor</h1><p>Dashboard not found</p>"


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel():
    """Serve the admin panel."""
    admin_path = Path("templates/admin.html")
    if admin_path.exists():
        return admin_path.read_text()
    return "<h1>NetMon Admin Panel</h1><p>Admin panel not found</p>"


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
    }


@app.post("/api/auth/login", response_model=LoginResponse)
def login(login_data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token."""
    user = authenticate_user(login_data.username, login_data.password)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    # Create access token
    access_token = create_access_token(data={"sub": user["username"], "role": user["role"]})
    
    # Log authentication
    audit_log = AuditLogModel(
        username=user["username"],
        action="login",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_log)
    db.commit()
    
    return LoginResponse(
        access_token=access_token,
        user=user,
    )


@app.get("/api/windows")
def get_windows(
    limit: Optional[int] = Query(None, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get all traffic windows (public endpoint)."""
    query = db.query(WindowModel).order_by(WindowModel.start_time.desc())
    
    if limit:
        query = query.limit(limit)
    
    windows = query.all()
    
    # Convert to dict format
    result = []
    for w in windows:
        result.append({
            "id": w.id,
            "metrics": {
                "start_time": w.start_time.isoformat(),
                "end_time": w.end_time.isoformat(),
                "total_flows": w.total_flows,
                "total_packets": w.total_packets,
                "benign_flows": w.benign_flows,
                "attack_flows": w.attack_flows,
                "unknown_flows": w.unknown_flows,
                "attacks_per_label": w.attacks_per_label or {},
                "total_payload_bytes": w.total_payload_bytes,
                "feature_stats": w.feature_stats or {},
            },
            "llm_summary": w.llm_summary or "",
        })
    
    return result


@app.get("/api/windows/latest")
def get_latest_window(db: Session = Depends(get_db)):
    """Get the latest traffic window."""
    window = db.query(WindowModel).order_by(WindowModel.end_time.desc()).first()
    
    if not window:
        raise HTTPException(status_code=404, detail="No windows available")
    
    return {
        "id": window.id,
        "metrics": {
            "start_time": window.start_time.isoformat(),
            "end_time": window.end_time.isoformat(),
            "total_flows": window.total_flows,
            "total_packets": window.total_packets,
            "benign_flows": window.benign_flows,
            "attack_flows": window.attack_flows,
            "unknown_flows": window.unknown_flows,
            "attacks_per_label": window.attacks_per_label or {},
            "total_payload_bytes": window.total_payload_bytes,
            "feature_stats": window.feature_stats or {},
        },
        "llm_summary": window.llm_summary or "",
    }


@app.get("/api/config/public")
def get_public_config_endpoint():
    """Get public configuration (read-only for all users)."""
    config = get_public_config()
    return config.to_dict()


@app.put("/api/config/public")
def update_public_config(
    updates: ConfigUpdateRequest,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update public configuration (authenticated users)."""
    config = get_public_config()
    config.update(updates.updates)
    
    # Log configuration change
    audit_log = AuditLogModel(
        username=current_user["username"],
        action="config_update",
        resource="public_config",
        details={"updates": updates.updates},
    )
    db.add(audit_log)
    db.commit()
    
    return {"status": "updated", "config": config.to_dict()}


@app.get("/api/alerts")
def get_alerts(
    acknowledged: Optional[bool] = Query(None),
    resolved: Optional[bool] = Query(None),
    severity: Optional[str] = Query(None),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Get alerts (public endpoint)."""
    query = db.query(AlertModel).order_by(AlertModel.created_at.desc())
    
    if acknowledged is not None:
        query = query.filter(AlertModel.acknowledged == acknowledged)
    if resolved is not None:
        query = query.filter(AlertModel.resolved == resolved)
    if severity:
        query = query.filter(AlertModel.severity == severity)
    
    alerts = query.limit(limit).all()
    
    return [
        {
            "id": a.id,
            "window_id": a.window_id,
            "alert_type": a.alert_type,
            "severity": a.severity,
            "title": a.title,
            "message": a.message,
            "metadata": a.metadata or {},
            "acknowledged": a.acknowledged,
            "resolved": a.resolved,
            "created_at": a.created_at.isoformat(),
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        }
        for a in alerts
    ]


@app.get("/api/analytics/summary")
def get_analytics_summary(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
):
    """Get analytics summary (public endpoint)."""
    query = db.query(WindowModel)
    
    if start_time:
        query = query.filter(WindowModel.start_time >= start_time)
    if end_time:
        query = query.filter(WindowModel.end_time <= end_time)
    
    windows = query.all()
    
    if not windows:
        return {
            "total_windows": 0,
            "total_flows": 0,
            "total_packets": 0,
            "total_attack_flows": 0,
            "total_benign_flows": 0,
            "attack_percentage": 0.0,
            "average_flows_per_window": 0.0,
        }
    
    total_flows = sum(w.total_flows for w in windows)
    total_packets = sum(w.total_packets for w in windows)
    total_attack_flows = sum(w.attack_flows for w in windows)
    total_benign_flows = sum(w.benign_flows for w in windows)
    
    attack_percentage = (total_attack_flows / total_flows * 100) if total_flows > 0 else 0.0
    avg_flows = total_flows / len(windows) if windows else 0.0
    
    return {
        "total_windows": len(windows),
        "total_flows": total_flows,
        "total_packets": total_packets,
        "total_attack_flows": total_attack_flows,
        "total_benign_flows": total_benign_flows,
        "attack_percentage": round(attack_percentage, 2),
        "average_flows_per_window": round(avg_flows, 2),
        "time_range": {
            "start": min(w.start_time for w in windows).isoformat(),
            "end": max(w.end_time for w in windows).isoformat(),
        },
    }


# ==================== Admin Endpoints ====================

@app.get("/api/admin/config")
def get_admin_config_endpoint(
    current_user: Dict = Depends(require_admin),
):
    """Get admin configuration (admin only)."""
    config = get_admin_config()
    return config.to_dict()


@app.put("/api/admin/config")
def update_admin_config(
    updates: ConfigUpdateRequest,
    current_user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update admin configuration (admin only)."""
    config = get_admin_config()
    config.update(updates.updates)
    
    # Log configuration change
    audit_log = AuditLogModel(
        username=current_user["username"],
        action="config_update",
        resource="admin_config",
        details={"updates": updates.updates},
    )
    db.add(audit_log)
    db.commit()
    
    return {"status": "updated", "config": config.to_dict()}


@app.post("/api/admin/users")
def create_user_endpoint(
    user_data: UserCreateRequest,
    current_user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user (admin only)."""
    try:
        user = create_user(user_data.username, user_data.password, user_data.role)
        
        audit_log = AuditLogModel(
            username=current_user["username"],
            action="user_create",
            resource=user_data.username,
            details={"role": user_data.role},
        )
        db.add(audit_log)
        db.commit()
        
        return {"status": "created", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/admin/users")
def list_users_endpoint(
    current_user: Dict = Depends(require_admin),
):
    """List all users (admin only)."""
    return list_users()


@app.put("/api/admin/users/{username}/password")
def update_user_password_endpoint(
    username: str,
    password_data: PasswordUpdateRequest,
    current_user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update a user's password (admin only)."""
    try:
        update_user_password(username, password_data.new_password)
        
        audit_log = AuditLogModel(
            username=current_user["username"],
            action="user_password_update",
            resource=username,
        )
        db.add(audit_log)
        db.commit()
        
        return {"status": "updated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/admin/password")
def update_own_password(
    password_data: PasswordUpdateRequest,
    current_user: Dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update own password (authenticated users)."""
    # Verify current password
    from app.auth import load_users, verify_password
    users = load_users()
    user = users.get(current_user["username"])
    
    if not user or not verify_password(password_data.current_password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    
    update_user_password(current_user["username"], password_data.new_password)
    
    audit_log = AuditLogModel(
        username=current_user["username"],
        action="password_update",
        resource="self",
    )
    db.add(audit_log)
    db.commit()
    
    return {"status": "updated"}


@app.post("/api/admin/alerts/{alert_id}/acknowledge")
def acknowledge_alert(
    alert_id: int,
    current_user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Acknowledge an alert (admin only)."""
    alert = db.query(AlertModel).filter(AlertModel.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.acknowledged = True
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    
    return {"status": "acknowledged"}


@app.post("/api/admin/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    current_user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Resolve an alert (admin only)."""
    alert = db.query(AlertModel).filter(AlertModel.id == alert_id).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.resolved = True
    alert.resolved_at = datetime.now(timezone.utc)
    db.commit()
    
    return {"status": "resolved"}


@app.get("/api/admin/audit-logs")
def get_audit_logs(
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: Optional[int] = Query(100, ge=1, le=1000),
    current_user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Get audit logs (admin only)."""
    query = db.query(AuditLogModel).order_by(AuditLogModel.created_at.desc())
    
    if username:
        query = query.filter(AuditLogModel.username == username)
    if action:
        query = query.filter(AuditLogModel.action == action)
    
    logs = query.limit(limit).all()
    
    return [
        {
            "id": log.id,
            "username": log.username,
            "action": log.action,
            "resource": log.resource,
            "details": log.details or {},
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]


@app.get("/api/admin/export/csv")
def export_windows_csv(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    current_user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export windows data as CSV (admin only)."""
    query = db.query(WindowModel).order_by(WindowModel.start_time)
    
    if start_time:
        query = query.filter(WindowModel.start_time >= start_time)
    if end_time:
        query = query.filter(WindowModel.end_time <= end_time)
    
    windows = query.all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "ID", "Start Time", "End Time", "Total Flows", "Total Packets",
        "Benign Flows", "Attack Flows", "Unknown Flows", "Attack Percentage",
        "Total Payload Bytes", "Attacks Per Label"
    ])
    
    # Write data
    for w in windows:
        attack_pct = (w.attack_flows / w.total_flows * 100) if w.total_flows > 0 else 0.0
        writer.writerow([
            w.id,
            w.start_time.isoformat(),
            w.end_time.isoformat(),
            w.total_flows,
            w.total_packets,
            w.benign_flows,
            w.attack_flows,
            w.unknown_flows,
            f"{attack_pct:.2f}%",
            w.total_payload_bytes,
            json.dumps(w.attacks_per_label or {}),
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=netmon_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"},
    )


@app.get("/api/admin/export/json")
def export_windows_json(
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    current_user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Export windows data as JSON (admin only)."""
    query = db.query(WindowModel).order_by(WindowModel.start_time)
    
    if start_time:
        query = query.filter(WindowModel.start_time >= start_time)
    if end_time:
        query = query.filter(WindowModel.end_time <= end_time)
    
    windows = query.all()
    
    data = [
        {
            "id": w.id,
            "metrics": {
                "start_time": w.start_time.isoformat(),
                "end_time": w.end_time.isoformat(),
                "total_flows": w.total_flows,
                "total_packets": w.total_packets,
                "benign_flows": w.benign_flows,
                "attack_flows": w.attack_flows,
                "unknown_flows": w.unknown_flows,
                "attacks_per_label": w.attacks_per_label or {},
                "total_payload_bytes": w.total_payload_bytes,
                "feature_stats": w.feature_stats or {},
            },
            "llm_summary": w.llm_summary or "",
        }
        for w in windows
    ]
    
    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=netmon_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"},
    )


@app.get("/api/user/me")
def get_current_user_info(
    current_user: Dict = Depends(get_current_user),
):
    """Get current user information."""
    return current_user


@app.get("/api/system/status")
def get_system_status(db: Session = Depends(get_db)):
    """Get comprehensive system status (public endpoint)."""
    from app.config import get_admin_config
    from app.alerts import get_unacknowledged_alerts_count, get_critical_alerts_count
    
    admin_config = get_admin_config()
    
    # Get recent windows count
    recent_windows = db.query(WindowModel).filter(
        WindowModel.created_at >= datetime.now(timezone.utc) - timedelta(hours=1)
    ).count()
    
    # Get alert counts
    unacknowledged = get_unacknowledged_alerts_count(db)
    critical = get_critical_alerts_count(db)
    
    # Check ML model status
    from app.ml_model import model_is_ready
    ml_ready = model_is_ready()
    
    # Get worker health
    try:
        from app.worker import get_worker_health
        worker_health = get_worker_health()
        worker_status = worker_health.get("status", "unknown")
    except Exception:
        worker_status = "unknown"
    
    return {
        "status": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {
            "api": "operational",
            "worker": worker_status,
            "database": "operational",
            "ml_model": "ready" if ml_ready else "not_configured",
            "llm": "ready" if admin_config.llm.get("enabled", True) else "disabled",
        },
        "metrics": {
            "recent_windows": recent_windows,
            "unacknowledged_alerts": unacknowledged,
            "critical_alerts": critical,
        },
        "version": "2.0.0",
    }


@app.get("/api/worker/health")
def get_worker_health_endpoint():
    """Get worker health status (public endpoint)."""
    try:
        from app.worker import get_worker_health
        return get_worker_health()
    except Exception as e:
        return {
            "status": "unknown",
            "error": str(e),
            "running": False,
        }


@app.get("/api/worker/metrics")
def get_worker_metrics_endpoint(current_user: Dict = Depends(get_current_user)):
    """Get worker performance metrics (authenticated endpoint)."""
    try:
        from app.worker import get_worker_metrics
        metrics = get_worker_metrics()
        return metrics.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get worker metrics: {str(e)}")


@app.get("/api/admin/worker/status")
def get_admin_worker_status(current_user: Dict = Depends(require_admin)):
    """Get detailed worker status for admin (admin only)."""
    try:
        from app.worker import get_worker_health, get_worker_metrics
        from app.config import get_admin_config
        
        health = get_worker_health()
        metrics = get_worker_metrics()
        config = get_admin_config()
        
        return {
            "health": health,
            "metrics": metrics.to_dict(),
            "configuration": {
                "worker_interval_seconds": config.capture.get("worker_interval_seconds", 60),
                "max_windows_keep": config.capture.get("max_windows_keep", 12),
                "window_duration_minutes": config.capture.get("window_duration_minutes", 5),
                "ml_enabled": config.ml.get("enabled", True),
                "llm_enabled": config.llm.get("enabled", True),
                "parallel_processing": config.ntlflowlyzer.get("parallel_processing", False),
                "max_retries": config.ntlflowlyzer.get("max_retries", 3),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get worker status: {str(e)}")
