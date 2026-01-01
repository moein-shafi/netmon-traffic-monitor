"""
Enhanced worker that uses configuration system and database.
This is an improved version that integrates with the new architecture.
"""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

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

# Get configuration
admin_config = get_admin_config()

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


def run_ntlflowlyzer_for_pcap(pcap_path: Path, csv_path: Path) -> None:
    """Run NTLFlowLyzer on a single PCAP -> CSV using a JSON config."""
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
    with cfg_path.open("w") as f:
        json.dump(cfg, f, indent=2)

    print(f"[worker] Running NTLFlowLyzer for {pcap_path}", flush=True)
    completed = subprocess.run(
        [NTL_BIN, "-c", str(cfg_path)],
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        print(f"[worker] NTLFlowLyzer FAILED (rc={completed.returncode}) for {pcap_path}", flush=True)
        print(f"[worker] stdout:\n{completed.stdout}", flush=True)
        print(f"[worker] stderr:\n{completed.stderr}", flush=True)
        raise RuntimeError(f"NTLFlowLyzer error for {pcap_path}")
    else:
        print(f"[worker] NTLFlowLyzer OK for {pcap_path}", flush=True)

    try:
        cfg_path.unlink()
    except FileNotFoundError:
        pass


def process_pcaps_to_csv() -> None:
    """Find new PCAP files and convert them to CSV if not already processed."""
    PCAP_DIR.mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    pcap_files = sorted(PCAP_DIR.glob("window-*.pcap"))
    now = datetime.now(timezone.utc)

    print(f"[worker] Found {len(pcap_files)} pcap files", flush=True)

    for pcap in pcap_files:
        window_id = pcap.stem
        csv_path = CSV_DIR / f"{window_id}.csv"

        # Skip if CSV already exists
        if csv_path.exists():
            continue

        # Avoid very fresh files (tcpdump may still be writing)
        mtime = datetime.fromtimestamp(pcap.stat().st_mtime, tz=timezone.utc)
        age_sec = (now - mtime).total_seconds()
        if age_sec < 10:
            continue

        print(f"[worker] Processing new pcap {pcap} -> {csv_path}", flush=True)
        try:
            run_ntlflowlyzer_for_pcap(pcap, csv_path)
        except Exception as e:
            print(f"[worker] ERROR processing {pcap}: {e}", flush=True)


def summarise_features_and_ml(csv_path: Path):
    """Summarize features and run ML classification."""
    flows_count = 0
    total_packets = 0
    total_payload_bytes = 0

    series: Dict[str, List[float]] = {feat: [] for feat in FEATURES_OF_INTEREST}

    benign_flows = 0
    attack_flows = 0
    unknown_flows = 0
    attacks_per_label: Dict[str, int] = {}

    use_model = model_is_ready() and admin_config.ml.get("enabled", True)

    with csv_path.open("r") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        print(f"[worker]   CSV header for {csv_path.name}: {header}", flush=True)

        for row in reader:
            flows_count += 1

            # Aggregate traffic stats
            pkt_val = _get_numeric_from_row(row, FEATURE_COLUMN_ALIASES["packets_count"])
            if pkt_val is not None:
                total_packets += int(pkt_val)

            payload_val = _get_numeric_from_row(row, FEATURE_COLUMN_ALIASES["total_payload_bytes"])
            if payload_val is not None:
                total_payload_bytes += int(payload_val)

            for canonical_name in FEATURES_OF_INTEREST:
                value = _get_numeric_from_row(row, FEATURE_COLUMN_ALIASES[canonical_name])
                if value is not None:
                    series[canonical_name].append(value)

            # ML classification per flow
            if use_model:
                label = classify_row(row)
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

    if not use_model:
        benign_flows = flows_count
        attack_flows = 0
        unknown_flows = 0
        attacks_per_label = {}

    feature_stats: Dict[str, FeatureStats] = {}
    for feat, values in series.items():
        if not values:
            continue
        mean_v = sum(values) / len(values)
        min_v = min(values)
        max_v = max(values)
        feature_stats[feat] = FeatureStats(mean=mean_v, min=min_v, max=max_v)

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

    # Flow volume
    if flows < 20:
        flow_desc = "very low flow volume (only a handful of connections)"
    elif flows < 100:
        flow_desc = "low flow volume (a few dozen connections)"
    elif flows < 500:
        flow_desc = "moderate flow volume (hundreds of connections)"
    else:
        flow_desc = "high flow volume (many concurrent connections)"

    # Payload volume
    if bytes_total < 1e5:
        payload_desc = "small overall payload size"
    elif bytes_total < 1e6:
        payload_desc = "light to moderate payload volume"
    elif bytes_total < 1e7:
        payload_desc = "substantial payload volume"
    else:
        payload_desc = "very heavy payload volume"

    # Packet rate
    pkt_rate = packets / duration_sec
    if pkt_rate < 10:
        pkt_desc = "low packet rate"
    elif pkt_rate < 100:
        pkt_desc = "moderate packet rate"
    elif pkt_rate < 1000:
        pkt_desc = "elevated packet rate"
    else:
        pkt_desc = "very high packet rate that may indicate bursts"

    # ML classification summary
    if flows > 0:
        benign_pct = 100.0 * benign / flows if flows else 0.0
        attack_pct = 100.0 * attack / flows if flows else 0.0
        unknown_pct = 100.0 * unknown / flows if flows else 0.0
        ml_line = (
            f"In this window, the detection model classified approximately "
            f"{benign} flows ({benign_pct:.1f}%) as benign, "
            f"{attack} flows ({attack_pct:.1f}%) as attack, and "
            f"{unknown} flows ({unknown_pct:.1f}%) as unknown / needs investigation."
        )
    else:
        ml_line = "No flows were exported in this window."

    # Top attack labels
    attack_labels = [(lbl, cnt) for lbl, cnt in label_counts.items() if lbl != "Unknown"]
    attack_labels.sort(key=lambda kv: kv[1], reverse=True)
    if attack_labels:
        top_str = ", ".join(f"{lbl}: {cnt}" for lbl, cnt in attack_labels[:3])
        ml_line2 = f"The most frequent attack-labelled classes: {top_str}."
    else:
        ml_line2 = "No specific attack class stands out."

    lines = [
        f"- Window: {start.isoformat()} to {end.isoformat()} (UTC).",
        f"- Traffic volume: {flow_desc} with {payload_desc} and a {pkt_desc}.",
        f"- ML classifier: {ml_line}",
        f"- ML label mix: {ml_line2}",
    ]

    return "\n".join(lines)


def generate_llm_summary(window_id: str, metrics: WindowMetrics) -> str:
    """Generate LLM summary if enabled, otherwise use rule-based."""
    if not OLLAMA_ENABLED:
        return build_rule_based_summary(window_id, metrics)
    
    base_summary = build_rule_based_summary(window_id, metrics)

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": (
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
        ),
        "stream": False,
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        raw = (data.get("response") or "").strip()
        if not raw:
            print(f"[worker] LLM returned empty text for {window_id}, falling back to rule-based summary.", flush=True)
            return base_summary

        print(f"[worker] LLM summary generated for {window_id}", flush=True)
        return raw

    except Exception as e:
        print(f"[worker] LLM error for {window_id}: {e} — falling back to rule-based summary.", flush=True)
        return base_summary


def save_window_to_db(window: Window, db: Session) -> WindowModel:
    """Save a window to the database."""
    # Check if window already exists
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


def process_csvs_to_windows() -> None:
    """Convert CSVs into Window objects and save to database."""
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()

    try:
        csv_files = sorted(CSV_DIR.glob("window-*.csv"))
        print(f"[worker] Found {len(csv_files)} csv files", flush=True)

        for csv_path in csv_files:
            window_id = csv_path.stem
            
            # Check if already processed
            existing = db.query(WindowModel).filter(WindowModel.id == window_id).first()
            if existing:
                continue

            print(f"[worker] Summarising {csv_path}", flush=True)
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
                print(f"[worker]   -> no flows in {csv_path}, skipping", flush=True)
                continue

            start_time, end_time = parse_window_times(window_id)

            metrics = WindowMetrics(
                start_time=start_time,
                end_time=end_time,
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
            
            # Check and create alerts
            try:
                alerts = check_and_create_alerts(db_window, db)
                if alerts:
                    print(f"[worker] Created {len(alerts)} alert(s) for window {window_id}", flush=True)
            except Exception as e:
                print(f"[worker] Error creating alerts for {window_id}: {e}", flush=True)

        # Clean up old windows (keep only MAX_WINDOWS)
        all_windows = db.query(WindowModel).order_by(WindowModel.start_time.desc()).all()
        if len(all_windows) > MAX_WINDOWS:
            windows_to_delete = all_windows[MAX_WINDOWS:]
            for w in windows_to_delete:
                db.delete(w)
            db.commit()
            print(f"[worker] Pruned {len(windows_to_delete)} old windows", flush=True)

    finally:
        db.close()


def main_loop() -> None:
    """Main worker loop."""
    print("[worker] Starting enhanced worker loop", flush=True)
    while True:
        try:
            # Reload config on each iteration (allows runtime config changes)
            global admin_config
            admin_config = get_admin_config()
            
            process_pcaps_to_csv()
        except Exception as e:
            print(f"[worker] ERROR in process_pcaps_to_csv: {e}", flush=True)

        try:
            process_csvs_to_windows()
        except Exception as e:
            print(f"[worker] ERROR in process_csvs_to_windows: {e}", flush=True)

        time.sleep(LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main_loop()

