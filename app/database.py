"""
Database models and session management for NetMon.
Uses SQLite with SQLAlchemy for better data management.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

DB_DIR = Path("/var/netmon/db")
DB_PATH = DB_DIR / "netmon.db"

DB_DIR.mkdir(parents=True, exist_ok=True)

# SQLite database
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,  # Set to True for SQL debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class WindowModel(Base):
    """SQLAlchemy model for traffic windows."""
    __tablename__ = "windows"

    id = Column(String, primary_key=True, index=True)
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=False, index=True)
    
    # Metrics
    total_flows = Column(Integer, default=0)
    total_packets = Column(Integer, default=0)
    total_payload_bytes = Column(Integer, default=0)
    benign_flows = Column(Integer, default=0)
    attack_flows = Column(Integer, default=0)
    unknown_flows = Column(Integer, default=0)
    
    # JSON fields for complex data
    attacks_per_label = Column(JSON, default=dict)
    feature_stats = Column(JSON, default=dict)
    
    # LLM summary
    llm_summary = Column(Text, default="")
    
    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AlertModel(Base):
    """SQLAlchemy model for alerts."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    window_id = Column(String, index=True)
    alert_type = Column(String, nullable=False, index=True)  # 'critical', 'elevated', 'info'
    severity = Column(String, nullable=False)  # 'high', 'medium', 'low'
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    alert_metadata = Column(JSON, default=dict)  # Renamed from 'metadata' (SQLAlchemy reserved)
    
    # Status
    acknowledged = Column(Boolean, default=False)
    resolved = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class AuditLogModel(Base):
    """SQLAlchemy model for audit logs."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)  # 'login', 'config_update', 'user_create', etc.
    resource = Column(String, nullable=True)  # What was affected
    details = Column(JSON, default=dict)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


# Create tables
def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Initialize database on import
init_db()

