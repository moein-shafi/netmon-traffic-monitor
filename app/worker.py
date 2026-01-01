"""
Enterprise-Grade Network Traffic Processing Worker
Advanced features: monitoring, metrics, health checks, performance tracking
Perfect for showcasing production-ready software engineering skills.
"""
from __future__ import annotations

import csv
import json
import time
import logging
import threading
import statistics
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager

import subprocess
import requests
from sqlalchemy.orm import Session

from app.storage import Window, WindowMetrics, FeatureStats
from app.ml_model import model_is_ready, classify_row
from app.config import get_admin_config
from app.database import SessionLocal, WindowModel, init_db
from app.alerts import check_and_create_alerts

# Initialize database
init_db()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Worker state and metrics
@dataclass
class WorkerMetrics:
    """Worker performance metrics."""
    start_time: datetime
    total_processed_pcaps: int = 0
    total_processed_csvs: int = 0
    total_processed_windows: int = 0
    total_flows_analyzed: int = 0
    total_alerts_created: int = 0
    total_errors: int = 0
    last_pcap_processed: Optional[datetime] = None
    last_csv_processed: Optional[datetime] = None
    last_window_processed: Optional[datetime] = None
    avg_processing_time_pcap: float = 0.0
    avg_processing_time_csv: float = 0.0
    avg_processing_time_window: float = 0.0
    ml_classifications: int = 0
    llm_summaries_generated: int = 0
    llm_summaries_failed: int = 0
    ntlflowlyzer_errors: int = 0
    database_errors: int = 0
    
    # Performance tracking
    processing_times_pcap: deque = None
    processing_times_csv: deque = None
    processing_times_window: deque = None
    
    def __post_init__(self):
        if self.processing_times_pcap is None:
            self.processing_times_pcap = deque(maxlen=100)
        if self.processing_times_csv is None:
            self.processing_times_csv = deque(maxlen=100)
        if self.processing_times_window is None:
            self.processing_times_window = deque(maxlen=100)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        for key, value in data.items():
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif isinstance(value, deque):
                data[key] = list(value)
        return data

# Global worker state
_worker_metrics = WorkerMetrics(start_time=datetime.now(timezone.utc))
_worker_lock = threading.Lock()
_worker_running = True
_worker_health_status = "healthy"

# Get configuration
def get_config():
    """Get current admin configuration."""
    return get_admin_config()

admin_config = get_config()

# Directories from config
PCAP_DIR = Path(admin_config.capture.get("pcap_dir", "/var/pcaps"))
CSV_DIR = Path(admin_config.capture.get("csv_dir", "/var/netmon/flows"))

# NTLFlowLyzer binary from config
NTL_BIN = admin_config.ntlflowlyzer.get("binary_path", "/opt/netmon/env/bin/ntlflowlyzer")

# Ollama settings from config
OLLAMA_URL = admin_config.llm.get("ollama_url", "http://127.0.0.1:11434/api/generate")
OLLAMA_MODEL = admin_config.llm.get("ollama_model", "smollm2:135m")
OLLAMA_ENABLED = admin_config.llm.get("enabled", True)
OLLAMA_TIMEOUT = admin_config.llm.get("timeout_seconds", 60)

# Keep only this many recent windows
MAX_WINDOWS = admin_config.capture.get("max_windows_keep", 12)
# Main loop interval
LOOP_INTERVAL_SECONDS = admin_config.capture.get("worker_interval_seconds", 60)

# Advanced processing settings
MAX_RETRIES = admin_config.ntlflowlyzer.get("max_retries", 3)
RETRY_DELAY = admin_config.ntlflowlyzer.get("retry_delay_seconds", 5)
PARALLEL_PROCESSING = admin_config.ntlflowlyzer.get("parallel_processing", False)
BATCH_SIZE = admin_config.ntlflowlyzer.get("batch_size", 10)

# Features we want aggregate stats for
FEATURE_COLUMN_ALIASES: Dict[str, List[str]] = {
    "duration": ["duration"],
    "packets_count": ["packets_count"],
    "total_payload_bytes": ["total_payload_bytes"],
    "bytes_rate": ["bytes_rate"],
    "packets_rate": ["packets_rate"],
    "active_mean": ["active_mean"],
    "idle_mean": ["idle_mean"],
    "fwd_packets_iat_mean": ["fwd_packets_iAT_mean", "fwd_packets_IAT_mean", "fwd_packets_iat_mean"],
    "bwd_packets_iat_mean": ["bwd_packets_iAT_mean", "bwd_packets_IAT_mean", "bwd_packets_iat_mean"],
}

FEATURES_OF_INTEREST: List[str] = list(FEATURE_COLUMN_ALIASES.keys())


@contextmanager
def track_processing_time(metric_deque: deque):
    """Context manager to track processing time."""
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        metric_deque.append(elapsed)


def update_metrics(func_name: str, **kwargs):
    """Update worker metrics."""
    with _worker_lock:
        if func_name == "pcap_processed":
            _worker_metrics.total_processed_pcaps += 1
            _worker_metrics.last_pcap_processed = datetime.now(timezone.utc)
            if kwargs.get("processing_time"):
                _worker_metrics.processing_times_pcap.append(kwargs["processing_time"])
                if _worker_metrics.processing_times_pcap:
                    _worker_metrics.avg_processing_time_pcap = statistics.mean(_worker_metrics.processing_times_pcap)
        elif func_name == "csv_processed":
            _worker_metrics.total_processed_csvs += 1
            _worker_metrics.last_csv_processed = datetime.now(timezone.utc)
            if kwargs.get("processing_time"):
                _worker_metrics.processing_times_csv.append(kwargs["processing_time"])
                if _worker_metrics.processing_times_csv:
                    _worker_metrics.avg_processing_time_csv = statistics.mean(_worker_metrics.processing_times_csv)
        elif func_name == "window_processed":
            _worker_metrics.total_processed_windows += 1
            _worker_metrics.last_window_processed = datetime.now(timezone.utc)
            if kwargs.get("processing_time"):
                _worker_metrics.processing_times_window.append(kwargs["processing_time"])
                if _worker_metrics.processing_times_window:
                    _worker_metrics.avg_processing_time_window = statistics.mean(_worker_metrics.processing_times_window)
        elif func_name == "flows_analyzed":
            _worker_metrics.total_flows_analyzed += kwargs.get("count", 0)
        elif func_name == "alert_created":
            _worker_metrics.total_alerts_created += kwargs.get("count", 0)
        elif func_name == "ml_classification":
            _worker_metrics.ml_classifications += kwargs.get("count", 0)
        elif func_name == "llm_success":
            _worker_metrics.llm_summaries_generated += 1
        elif func_name == "llm_failed":
            _worker_metrics.llm_summaries_failed += 1
        elif func_name == "error":
            _worker_metrics.total_errors += 1
            error_type = kwargs.get("type", "unknown")
            if error_type == "ntlflowlyzer":
                _worker_metrics.ntlflowlyzer_errors += 1
            elif error_type == "database":
                _worker_metrics.database_errors += 1


def get_worker_metrics() -> WorkerMetrics:
    """Get current worker metrics."""
    with _worker_lock:
        return _worker_metrics


def get_worker_health() -> Dict[str, Any]:
    """Get worker health status."""
    with _worker_lock:
        uptime = (datetime.now(timezone.utc) - _worker_metrics.start_time).total_seconds()
        
        # Check if worker is processing
        last_activity = max(
            _worker_metrics.last_pcap_processed or datetime.min.replace(tzinfo=timezone.utc),
            _worker_metrics.last_csv_processed or datetime.min.replace(tzinfo=timezone.utc),
            _worker_metrics.last_window_processed or datetime.min.replace(tzinfo=timezone.utc),
        )
        
        time_since_activity = (datetime.now(timezone.utc) - last_activity).total_seconds()
        
        # Determine health status
        if time_since_activity > LOOP_INTERVAL_SECONDS * 3:
            health = "degraded"
        elif _worker_metrics.total_errors > 10 and _worker_metrics.total_processed_windows > 0:
            error_rate = _worker_metrics.total_errors / _worker_metrics.total_processed_windows
            health = "degraded" if error_rate > 0.1 else "healthy"
        else:
            health = "healthy"
        
        return {
            "status": health,
            "running": _worker_running,
            "uptime_seconds": uptime,
            "last_activity": last_activity.isoformat() if last_activity != datetime.min.replace(tzinfo=timezone.utc) else None,
            "time_since_activity_seconds": time_since_activity if last_activity != datetime.min.replace(tzinfo=timezone.utc) else None,
            "metrics": _worker_metrics.to_dict(),
        }


def parse_window_times(window_id: str) -> Tuple[datetime, datetime]:
    """Parse window ID to start and end times."""
    ts_str = window_id.replace("window-", "")
    dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    window_duration = admin_config.capture.get("window_duration_minutes", 5)
    return dt, dt + timedelta(minutes=window_duration)


def _get_numeric_from_row(row: Dict[str, str], aliases: List[str]) -> Optional[float]:
    """Try all alias column names for a feature and return the first valid numeric value."""
    for col in aliases:
        if col in row and row[col] not in ("", None):
            try:
                return float(row[col])
            except ValueError:
                continue
    return None


def run_ntlflowlyzer_for_pcap(pcap_path: Path, csv_path: Path, retry_count: int = 0) -> bool:
    """
    Run NTLFlowLyzer on a single PCAP -> CSV using a JSON config.
    Returns True on success, False on failure.
    """
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    
    cfg = {
        "pcap_file_address": str(pcap_path),
        "output_file_address": str(csv_path),
        "label": "Unknown",
        "number_of_threads": admin_config.ntlflowlyzer.get("threads", 4),
        "feature_extractor_min_flows": admin_config.ntlflowlyzer.get("min_flows", 1),
        "writer_min_rows": admin_config.ntlflowlyzer.get("min_rows", 1),
        "max_rows_number": admin_config.ntlflowlyzer.get("max_rows", 800000),
    }
    
    cfg_path = csv_path.with_suffix(".json")
    try:
        with cfg_path.open("w") as f:
            json.dump(cfg, f, indent=2)
        
        logger.info(f"Running NTLFlowLyzer for {pcap_path.name}")
        start_time = time.time()
        
        completed = subprocess.run(
            [NTL_BIN, "-c", str(cfg_path)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        
        processing_time = time.time() - start_time
        
        if completed.returncode != 0:
            error_msg = f"NTLFlowLyzer failed (rc={completed.returncode}) for {pcap_path.name}"
            logger.error(f"{error_msg}\nstdout: {completed.stdout}\nstderr: {completed.stderr}")
            
            # Retry logic
            if retry_count < MAX_RETRIES:
                logger.info(f"Retrying ({retry_count + 1}/{MAX_RETRIES}) after {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                return run_ntlflowlyzer_for_pcap(pcap_path, csv_path, retry_count + 1)
            
            update_metrics("error", type="ntlflowlyzer")
            raise RuntimeError(error_msg)
        
        logger.info(f"NTLFlowLyzer completed for {pcap_path.name} in {processing_time:.2f}s")
        update_metrics("pcap_processed", processing_time=processing_time)
        return True
        
    except subprocess.TimeoutExpired:
        logger.error(f"NTLFlowLyzer timeout for {pcap_path.name}")
        update_metrics("error", type="ntlflowlyzer")
        return False
    except Exception as e:
        logger.error(f"Error running NTLFlowLyzer for {pcap_path.name}: {e}")
        update_metrics("error", type="ntlflowlyzer")
        return False
    finally:
        try:
            cfg_path.unlink()
        except FileNotFoundError:
            pass


def process_pcaps_to_csv() -> Dict[str, Any]:
    """
    Find new PCAP files and convert them to CSV if not already processed.
    Returns processing statistics.
    """
    PCAP_DIR.mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    
    pcap_files = sorted(PCAP_DIR.glob("window-*.pcap"))
    now = datetime.now(timezone.utc)
    
    stats = {
        "total_pcaps": len(pcap_files),
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "too_fresh": 0,
    }
    
    logger.info(f"Found {len(pcap_files)} PCAP files")
    
    for pcap in pcap_files:
        window_id = pcap.stem
        csv_path = CSV_DIR / f"{window_id}.csv"
        
        # Skip if CSV already exists
        if csv_path.exists():
            stats["skipped"] += 1
            continue
        
        # Avoid very fresh files (tcpdump may still be writing)
        try:
            mtime = datetime.fromtimestamp(pcap.stat().st_mtime, tz=timezone.utc)
            age_sec = (now - mtime).total_seconds()
            if age_sec < admin_config.capture.get("pcap_min_age_seconds", 10):
                stats["too_fresh"] += 1
                continue
        except Exception as e:
            logger.warning(f"Error checking mtime for {pcap.name}: {e}")
            continue
        
        logger.info(f"Processing PCAP: {pcap.name} -> {csv_path.name}")
        try:
            success = run_ntlflowlyzer_for_pcap(pcap, csv_path)
            if success:
                stats["processed"] += 1
            else:
                stats["errors"] += 1
        except Exception as e:
            logger.error(f"Error processing {pcap.name}: {e}")
            stats["errors"] += 1
            update_metrics("error", type="ntlflowlyzer")
    
    return stats


def summarise_features_and_ml(csv_path: Path) -> Tuple[int, int, int, Dict[str, FeatureStats], int, int, int, Dict[str, int]]:
    """
    Summarize features and run ML classification.
    Returns comprehensive statistics.
    """
    flows_count = 0
    total_packets = 0
    total_payload_bytes = 0
    
    series: Dict[str, List[float]] = {feat: [] for feat in FEATURES_OF_INTEREST}
    
    benign_flows = 0
    attack_flows = 0
    unknown_flows = 0
    attacks_per_label: Dict[str, int] = {}
    
    use_model = model_is_ready() and admin_config.ml.get("enabled", True)
    
    ml_classifications_count = 0
    
    try:
        with csv_path.open("r") as f:
            reader = csv.DictReader(f)
            header = reader.fieldnames or []
            logger.debug(f"CSV header for {csv_path.name}: {len(header)} columns")
            
            for row in reader:
                flows_count += 1
                
                # Aggregate traffic stats
                pkt_val = _get_numeric_from_row(row, FEATURE_COLUMN_ALIASES["packets_count"])
                if pkt_val is not None:
                    total_packets += int(pkt_val)
                
                payload_val = _get_numeric_from_row(row, FEATURE_COLUMN_ALIASES["total_payload_bytes"])
                if payload_val is not None:
                    total_payload_bytes += int(payload_val)
                
                # Collect feature values
                for canonical_name in FEATURES_OF_INTEREST:
                    value = _get_numeric_from_row(row, FEATURE_COLUMN_ALIASES[canonical_name])
                    if value is not None:
                        series[canonical_name].append(value)
                
                # ML classification per flow
                if use_model:
                    try:
                        label = classify_row(row)
                        ml_classifications_count += 1
                        if label is None:
                            continue
                        if label == "Benign":
                            benign_flows += 1
                        elif label == "Unknown":
                            unknown_flows += 1
                            attacks_per_label["Unknown"] = attacks_per_label.get("Unknown", 0) + 1
                        else:
                            attack_flows += 1
                            attacks_per_label[label] = attacks_per_label.get(label, 0) + 1
                    except Exception as e:
                        logger.warning(f"ML classification error for flow: {e}")
                        unknown_flows += 1
                        attacks_per_label["Unknown"] = attacks_per_label.get("Unknown", 0) + 1
        
        if not use_model:
            benign_flows = flows_count
            attack_flows = 0
            unknown_flows = 0
            attacks_per_label = {}
        
        # Calculate feature statistics
        feature_stats: Dict[str, FeatureStats] = {}
        for feat, values in series.items():
            if not values:
                continue
            mean_v = statistics.mean(values)
            min_v = min(values)
            max_v = max(values)
            feature_stats[feat] = FeatureStats(mean=mean_v, min=min_v, max=max_v)
        
        update_metrics("flows_analyzed", count=flows_count)
        update_metrics("ml_classification", count=ml_classifications_count)
        
        return (
            flows_count,
            total_packets,
            total_payload_bytes,
            feature_stats,
            benign_flows,
            attack_flows,
            unknown_flows,
            attacks_per_label,
        )
    
    except Exception as e:
        logger.error(f"Error processing CSV {csv_path.name}: {e}")
        update_metrics("error", type="csv_processing")
        raise


def build_rule_based_summary(window_id: str, metrics: WindowMetrics) -> str:
    """Build a deterministic, human-readable behavioural summary."""
    start = metrics.start_time
    end = metrics.end_time
    duration_sec = max((end - start).total_seconds(), 1.0)
    
    flows = metrics.total_flows
    packets = metrics.total_packets
    bytes_total = metrics.total_payload_bytes
    fs = metrics.feature_stats
    
    benign = metrics.benign_flows
    attack = metrics.attack_flows
    unknown = getattr(metrics, "unknown_flows", 0)
    label_counts = metrics.attacks_per_label or {}
    
    # Enhanced analysis
    lines = [
        f"Window: {start.isoformat()} to {end.isoformat()} (UTC)",
        f"Duration: {duration_sec:.1f} seconds",
        f"Total flows: {flows:,}",
        f"Total packets: {packets:,}",
        f"Total payload: {bytes_total / 1024 / 1024:.2f} MB",
    ]
    
    if flows > 0:
        benign_pct = 100.0 * benign / flows
        attack_pct = 100.0 * attack / flows
        unknown_pct = 100.0 * unknown / flows
        lines.append(f"Classification: {benign_pct:.1f}% benign, {attack_pct:.1f}% attack, {unknown_pct:.1f}% unknown")
    
    if label_counts:
        top_attacks = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        attack_str = ", ".join(f"{label} ({count})" for label, count in top_attacks)
        lines.append(f"Top attack types: {attack_str}")
    
    return "\n".join(lines)


def generate_llm_summary(window_id: str, metrics: WindowMetrics) -> str:
    """Generate LLM summary using configured provider, otherwise use rule-based."""
    from app.llm_providers import generate_with_llm, list_providers
    
    llm_config = admin_config.llm
    if not llm_config.get("enabled", True):
        return build_rule_based_summary(window_id, metrics)
    
    # Get configured provider
    provider = llm_config.get("provider", "ollama")
    model = llm_config.get("model", "smollm2:135m")
    timeout = llm_config.get("timeout_seconds", 60)
    provider_url = llm_config.get("provider_url")
    
    base_summary = build_rule_based_summary(window_id, metrics)
    
    prompt = (
        "You are a senior network security engineer writing notes for an internal monitoring dashboard.\n"
        "Below is a draft summary describing one 5-minute window of network traffic:\n\n"
        f"{base_summary}\n\n"
        "Rewrite this as 3–5 concise bullet points in a professional tone.\n"
        "IMPORTANT FORMAT RULES:\n"
        "- Output ONLY bullet points, nothing else.\n"
        "- Each bullet point MUST start with '- ' (dash + space).\n"
        "- Do NOT add titles, headings, section labels, or explanations.\n"
        "- Do NOT mention 'draft', 'rewrite', 'bullet points', or anything about the process.\n"
        "- Do NOT wrap the answer in quotes, backticks, or code fences.\n"
        "Just return the final bullet points."
    )
    
    try:
        kwargs = {}
        if provider_url:
            kwargs["url"] = provider_url
        
        result = generate_with_llm(provider, model, prompt, timeout=timeout, **kwargs)
        
        if not result:
            logger.warning(f"LLM returned empty text for {window_id}, using rule-based summary")
            update_metrics("llm_failed")
            return base_summary
        
        logger.info(f"LLM summary generated for {window_id} using {provider}/{model}")
        update_metrics("llm_success")
        return result
    
    except Exception as e:
        logger.warning(f"LLM error for {window_id} ({provider}/{model}): {e}, using rule-based summary")
        update_metrics("llm_failed")
        return base_summary


def save_window_to_db(window: Window, db: Session) -> WindowModel:
    """Save a window to the database with error handling."""
    try:
        existing = db.query(WindowModel).filter(WindowModel.id == window.id).first()
        
        if existing:
            # Update existing
            existing.start_time = window.metrics.start_time
            existing.end_time = window.metrics.end_time
            existing.total_flows = window.metrics.total_flows
            existing.total_packets = window.metrics.total_packets
            existing.total_payload_bytes = window.metrics.total_payload_bytes
            existing.benign_flows = window.metrics.benign_flows
            existing.attack_flows = window.metrics.attack_flows
            existing.unknown_flows = getattr(window.metrics, "unknown_flows", 0)
            existing.attacks_per_label = window.metrics.attacks_per_label or {}
            existing.feature_stats = {
                k: {"mean": v.mean, "min": v.min, "max": v.max}
                for k, v in (window.metrics.feature_stats or {}).items()
            }
            existing.llm_summary = window.llm_summary
            existing.updated_at = datetime.now(timezone.utc)
            db.commit()
            return existing
        else:
            # Create new
            db_window = WindowModel(
                id=window.id,
                start_time=window.metrics.start_time,
                end_time=window.metrics.end_time,
                total_flows=window.metrics.total_flows,
                total_packets=window.metrics.total_packets,
                total_payload_bytes=window.metrics.total_payload_bytes,
                benign_flows=window.metrics.benign_flows,
                attack_flows=window.metrics.attack_flows,
                unknown_flows=getattr(window.metrics, "unknown_flows", 0),
                attacks_per_label=window.metrics.attacks_per_label or {},
                feature_stats={
                    k: {"mean": v.mean, "min": v.min, "max": v.max}
                    for k, v in (window.metrics.feature_stats or {}).items()
                },
                llm_summary=window.llm_summary,
            )
            db.add(db_window)
            db.commit()
            db.refresh(db_window)
            return db_window
    except Exception as e:
        logger.error(f"Database error saving window {window.id}: {e}")
        db.rollback()
        update_metrics("error", type="database")
        raise


def process_csvs_to_windows() -> Dict[str, Any]:
    """
    Convert CSVs into Window objects and save to database.
    Returns processing statistics.
    """
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    
    stats = {
        "total_csvs": 0,
        "processed": 0,
        "skipped": 0,
        "errors": 0,
        "alerts_created": 0,
    }
    
    try:
        csv_files = sorted(CSV_DIR.glob("window-*.csv"))
        stats["total_csvs"] = len(csv_files)
        logger.info(f"Found {len(csv_files)} CSV files")
        
        for csv_path in csv_files:
            window_id = csv_path.stem
            start_time = time.time()
            
            # Check if already processed
            existing = db.query(WindowModel).filter(WindowModel.id == window_id).first()
            if existing:
                stats["skipped"] += 1
                continue
            
            logger.info(f"Processing CSV: {csv_path.name}")
            try:
                (
                    flows_count,
                    total_packets,
                    total_payload_bytes,
                    feature_stats,
                    benign_flows,
                    attack_flows,
                    unknown_flows,
                    attacks_per_label,
                ) = summarise_features_and_ml(csv_path)
                
                if flows_count == 0:
                    logger.warning(f"No flows in {csv_path.name}, skipping")
                    stats["skipped"] += 1
                    continue
                
                start_time_window, end_time_window = parse_window_times(window_id)
                
                metrics = WindowMetrics(
                    start_time=start_time_window,
                    end_time=end_time_window,
                    total_flows=flows_count,
                    total_packets=total_packets,
                    benign_flows=benign_flows,
                    attack_flows=attack_flows,
                    unknown_flows=unknown_flows,
                    attacks_per_label=attacks_per_label,
                    total_payload_bytes=total_payload_bytes,
                    feature_stats=feature_stats,
                )
                
                llm_summary = generate_llm_summary(window_id, metrics)
                window = Window(id=window_id, metrics=metrics, llm_summary=llm_summary)
                
                # Save to database
                db_window = save_window_to_db(window, db)
                processing_time = time.time() - start_time
                update_metrics("window_processed", processing_time=processing_time)
                stats["processed"] += 1
                
                # Check and create alerts
                try:
                    alerts = check_and_create_alerts(db_window, db)
                    if alerts:
                        alert_count = len(alerts)
                        stats["alerts_created"] += alert_count
                        update_metrics("alert_created", count=alert_count)
                        logger.info(f"Created {alert_count} alert(s) for window {window_id}")
                except Exception as e:
                    logger.error(f"Error creating alerts for {window_id}: {e}")
            
            except Exception as e:
                logger.error(f"Error processing CSV {csv_path.name}: {e}")
                stats["errors"] += 1
                update_metrics("error", type="csv_processing")
        
        # Clean up old windows (keep only MAX_WINDOWS)
        all_windows = db.query(WindowModel).order_by(WindowModel.start_time.desc()).all()
        if len(all_windows) > MAX_WINDOWS:
            windows_to_delete = all_windows[MAX_WINDOWS:]
            for w in windows_to_delete:
                db.delete(w)
            db.commit()
            logger.info(f"Pruned {len(windows_to_delete)} old windows")
        
        return stats
    
    finally:
        db.close()


def main_loop() -> None:
    """Main worker loop with comprehensive error handling and monitoring."""
    global _worker_running, admin_config
    
    logger.info("=" * 60)
    logger.info("NetMon Worker - Enterprise Edition")
    logger.info("Starting worker loop...")
    logger.info("=" * 60)
    
    iteration = 0
    
    while _worker_running:
        iteration += 1
        loop_start = time.time()
        
        try:
            # Reload config on each iteration (allows runtime config changes)
            admin_config = get_config()
            
            logger.info(f"Iteration {iteration} - Processing cycle")
            
            # Process PCAPs to CSV
            try:
                pcap_stats = process_pcaps_to_csv()
                logger.info(f"PCAP processing: {pcap_stats}")
            except Exception as e:
                logger.error(f"Error in process_pcaps_to_csv: {e}", exc_info=True)
                update_metrics("error", type="pcap_processing")
            
            # Process CSVs to windows
            try:
                csv_stats = process_csvs_to_windows()
                logger.info(f"CSV processing: {csv_stats}")
            except Exception as e:
                logger.error(f"Error in process_csvs_to_windows: {e}", exc_info=True)
                update_metrics("error", type="csv_processing")
            
            # Log metrics summary
            metrics = get_worker_metrics()
            loop_time = time.time() - loop_start
            logger.info(
                f"Cycle completed in {loop_time:.2f}s | "
                f"Total windows: {metrics.total_processed_windows} | "
                f"Total flows: {metrics.total_flows_analyzed:,} | "
                f"Total alerts: {metrics.total_alerts_created} | "
                f"Errors: {metrics.total_errors}"
            )
        
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down gracefully...")
            _worker_running = False
            break
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            update_metrics("error", type="main_loop")
        
        # Sleep with configurable interval
        sleep_time = admin_config.capture.get("worker_interval_seconds", 60)
        logger.debug(f"Sleeping for {sleep_time} seconds...")
        time.sleep(sleep_time)
    
    logger.info("Worker stopped")


def stop_worker():
    """Stop the worker gracefully."""
    global _worker_running
    logger.info("Stopping worker...")
    _worker_running = False


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
        stop_worker()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        raise
