from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import subprocess
import requests

from storage import Window, WindowMetrics, FeatureStats, load_windows, save_windows
from ml_model import model_is_ready, classify_row

# Directories
PCAP_DIR = Path("/var/pcaps")
CSV_DIR = Path("/var/netmon/flows")

# NTLFlowLyzer binary
NTL_BIN = "/opt/netmon/env/bin/ntlflowlyzer"

# Ollama settings
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "smollm2:135m"

# Keep only this many recent windows
MAX_WINDOWS = 12
# Main loop interval
LOOP_INTERVAL_SECONDS = 60

# Features we want aggregate stats for (these are present in your CSV header)
FEATURE_COLUMN_ALIASES: Dict[str, List[str]] = {
    "duration": ["duration"],
    "packets_count": ["packets_count"],
    "total_payload_bytes": ["total_payload_bytes"],
    "bytes_rate": ["bytes_rate"],
    "packets_rate": ["packets_rate"],
    "active_mean": ["active_mean"],
    "idle_mean": ["idle_mean"],
    # Handle both iat_mean / IAT_mean spellings
    "fwd_packets_iat_mean": ["fwd_packets_iAT_mean", "fwd_packets_IAT_mean", "fwd_packets_iat_mean"],
    "bwd_packets_iat_mean": ["bwd_packets_iAT_mean", "bwd_packets_IAT_mean", "bwd_packets_iat_mean"],
}

FEATURES_OF_INTEREST: List[str] = list(FEATURE_COLUMN_ALIASES.keys())


def parse_window_times(window_id: str) -> Tuple[datetime, datetime]:
    """
    window_id is like 'window-20251208115026'.
    We treat that as the start of the 5-minute window in UTC.
    """
    ts_str = window_id.replace("window-", "")
    dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return dt, dt + timedelta(minutes=5)


def _get_numeric_from_row(row: Dict[str, str], aliases: List[str]) -> Optional[float]:
    """
    Try all alias column names for a feature and return the first valid numeric value.
    If nothing is found or cannot be parsed, returns None.
    """
    for col in aliases:
        if col in row and row[col] not in ("", None):
            try:
                return float(row[col])
            except ValueError:
                continue
    return None


# ---------- Step 1: PCAP -> CSV via NTLFlowLyzer ----------

def run_ntlflowlyzer_for_pcap(pcap_path: Path, csv_path: Path) -> None:
    """Run NTLFlowLyzer on a single PCAP -> CSV using a JSON config."""
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    cfg = {
        "pcap_file_address": str(pcap_path),
        "output_file_address": str(csv_path),
        "label": "Unknown",
        "number_of_threads": 4,
        "feature_extractor_min_flows": 1,
        "writer_min_rows": 1,
        "max_rows_number": 800000,
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
        window_id = pcap.stem  # window-YYYYmmddHHMMSS
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


# ---------- Step 2: CSV -> metrics (including ML) + summaries ----------

def summarise_features_and_ml(csv_path: Path):
    """
    Returns:
      total_flows, total_packets, total_payload_bytes,
      feature_stats,
      benign_flows, attack_flows, unknown_flows, attacks_per_label
    """
    flows_count = 0
    total_packets = 0
    total_payload_bytes = 0

    series: Dict[str, List[float]] = {feat: [] for feat in FEATURES_OF_INTEREST}

    benign_flows = 0
    attack_flows = 0
    unknown_flows = 0
    attacks_per_label: Dict[str, int] = {}

    use_model = model_is_ready()

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
        # fall back: treat everything as benign if model not available
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
    """
    Build a deterministic, human-readable behavioural summary from
    traffic stats + ML output.
    """
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

    # --- Flow volume ---
    if flows < 20:
        flow_desc = "very low flow volume (only a handful of connections)"
    elif flows < 100:
        flow_desc = "low flow volume (a few dozen connections)"
    elif flows < 500:
        flow_desc = "moderate flow volume (hundreds of connections)"
    else:
        flow_desc = "high flow volume (many concurrent connections)"

    # --- Payload volume ---
    if bytes_total < 1e5:
        payload_desc = "small overall payload size"
    elif bytes_total < 1e6:
        payload_desc = "light to moderate payload volume"
    elif bytes_total < 1e7:
        payload_desc = "substantial payload volume"
    else:
        payload_desc = "very heavy payload volume"

    # --- Packet rate over the window ---
    pkt_rate = packets / duration_sec
    if pkt_rate < 10:
        pkt_desc = "low packet rate"
    elif pkt_rate < 100:
        pkt_desc = "moderate packet rate"
    elif pkt_rate < 1000:
        pkt_desc = "elevated packet rate"
    else:
        pkt_desc = "very high packet rate that may indicate bursts"

    # --- Flow duration behaviour ---
    duration_stats = fs.get("duration")
    if duration_stats:
        max_d = duration_stats.max
        mean_d = duration_stats.mean
        if max_d < 1:
            dur_desc = (
                "flows are almost all short-lived, consistent with quick request/response traffic "
                "or small control exchanges."
            )
        elif max_d < 30:
            dur_desc = (
                "flows show a mix of short and medium-lived connections, typical of web browsing or API usage."
            )
        elif max_d < 300:
            if mean_d < 10:
                dur_desc = (
                    "traffic is dominated by short flows with a few longer sessions, such as logged-in users "
                    "or background sync jobs."
                )
            else:
                dur_desc = (
                    "there are several longer-lived sessions alongside shorter traffic, which fits persistent "
                    "application connections."
                )
        else:
            dur_desc = (
                "there are long-lived flows that may correspond to persistent sessions (e.g., tunnels, streaming, "
                "remote shells) and could merit a closer look."
            )
    else:
        dur_desc = "flow duration distribution is not available for this window."

    # --- Rate / burstiness ---
    burst_desc = "no strong indication of aggressive bursts based on the available rate statistics."
    bytes_rate_stats = fs.get("bytes_rate")
    packets_rate_stats = fs.get("packets_rate")
    if bytes_rate_stats and packets_rate_stats:
        if (
            bytes_rate_stats.mean > 0 and bytes_rate_stats.max > 5 * bytes_rate_stats.mean
        ) or (
            packets_rate_stats.mean > 0 and packets_rate_stats.max > 5 * packets_rate_stats.mean
        ):
            burst_desc = (
                "traffic shows some bursty behaviour with short spikes in throughput, still within a realistic range "
                "for normal usage (e.g., page loads or short file transfers)."
            )

    # --- Packet timing / IAT behaviour ---
    f_iat = fs.get("fwd_packets_iat_mean")
    b_iat = fs.get("bwd_packets_iat_mean")
    if f_iat and b_iat:
        if f_iat.mean == 0.0 and b_iat.mean == 0.0:
            iat_desc = (
                "packet-level timing features are mostly zero in this export, so detailed inter-arrival analysis "
                "is limited."
            )
        else:
            iat_desc = (
                "forward and backward packet inter-arrival times look broadly consistent with interactive or web-style "
                "traffic rather than extremely tight, scan-like bursts."
            )
    else:
        iat_desc = (
            "packet-level timing features are not fully available for this window, so inter-arrival analysis is limited."
        )

    # --- ML classification summary ---
    if flows > 0:
        benign_pct = 100.0 * benign / flows if flows else 0.0
        attack_pct = 100.0 * attack / flows if flows else 0.0
        unknown_pct = 100.0 * unknown / flows if flows else 0.0
        ml_line = (
            f"In this 5-minute window, the detection model classified approximately "
            f"{benign} flows ({benign_pct:.1f}%) as benign, "
            f"{attack} flows ({attack_pct:.1f}%) as attack, and "
            f"{unknown} flows ({unknown_pct:.1f}%) as unknown / needs investigation."
        )
    else:
        ml_line = "No flows were exported in this window, so the detection model has nothing to evaluate."

    # Top attack labels (excluding 'Unknown')
    attack_labels = [(lbl, cnt) for lbl, cnt in label_counts.items() if lbl != "Unknown"]
    attack_labels.sort(key=lambda kv: kv[1], reverse=True)
    if attack_labels:
        top_str = ", ".join(f"{lbl}: {cnt}" for lbl, cnt in attack_labels[:3])
        ml_line2 = f"The most frequent attack-labelled classes in this slice are: {top_str}."
    else:
        ml_line2 = "No specific attack class stands out in this time slice."

    # --- Risk perspective ---
    risk_line = (
        "From a volume and timing perspective, this slice does not strongly resemble a classic volumetric DDoS. "
        "However, any non-trivial number of attack or unknown-labelled flows should be reviewed in context (e.g., "
        "source/destination, application logs, and historical baselines)."
    )

    lines = [
        f"- Window: {start.isoformat()} to {end.isoformat()} (UTC).",
        f"- Traffic volume: {flow_desc} with {payload_desc} and a {pkt_desc} over the 5-minute window.",
        f"- Flow behaviour: {dur_desc}",
        f"- Rate / burstiness: {burst_desc}",
        f"- Packet timing: {iat_desc}",
        f"- ML classifier: {ml_line}",
        f"- ML label mix: {ml_line2}",
        f"- Security perspective: {risk_line}",
    ]

    return "\n".join(lines)


def generate_llm_summary(window_id: str, metrics: WindowMetrics) -> str:
    """
    1) Build rule-based behavioural + ML summary.
    2) Ask LLM to rewrite it as clean bullet points.
    3) If LLM fails or misbehaves, fall back to rule-based text.
    """
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
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        raw = (data.get("response") or "").strip()
        if not raw:
            print(f"[worker] LLM returned empty text for {window_id}, falling back to rule-based summary.", flush=True)
            return base_summary

#        lines = [line.strip() for line in raw.splitlines() if line.strip().startswith("-")]
#        lines = [line.strip() for line in raw.splitlines()]
#        if not lines:
#            print(f"[worker] LLM returned no valid bullets for {window_id}, falling back to rule-based summary.", flush=True)
#            return base_summary

#        cleaned = "\n".join(lines[:5])
        cleaned = raw
#        print(f"[worker] LLM summary generated for {window_id}: {cleaned[:80]}...", flush=True)
        print(f"[worker] LLM summary generated for {window_id}: {raw}...", flush=True)
        return cleaned

    except Exception as e:
        print(f"[worker] LLM error for {window_id}: {e} — falling back to rule-based summary.", flush=True)
        return base_summary


def prune_files_by_windows(windows: List[Window]) -> None:
    """
    Keep PCAP/CSV only for windows we kept. Everything else is deleted.
    """
    keep_ids = {w.id for w in windows}
    deleted_pcap = 0
    deleted_csv = 0

    for pcap in PCAP_DIR.glob("window-*.pcap"):
        if pcap.stem not in keep_ids:
            try:
                pcap.unlink()
                deleted_pcap += 1
            except Exception as e:
                print(f"[worker] Failed to delete pcap {pcap}: {e}", flush=True)

    for csv_file in CSV_DIR.glob("window-*.csv"):
        if csv_file.stem not in keep_ids:
            try:
                csv_file.unlink()
                deleted_csv += 1
            except Exception as e:
                print(f"[worker] Failed to delete csv {csv_file}: {e}", flush=True)

    if deleted_pcap or deleted_csv:
        print(f"[worker] Pruned {deleted_pcap} pcaps and {deleted_csv} csv files", flush=True)


def process_csvs_to_windows() -> None:
    """
    Convert CSVs into Window objects with metrics + ML + LLM summary,
    save them to /var/netmon/windows.json,
    and prune old PCAP/CSV files.
    """
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    windows = load_windows()
    processed_ids = {w.id for w in windows}

    csv_files = sorted(CSV_DIR.glob("window-*.csv"))
    print(f"[worker] Found {len(csv_files)} csv files", flush=True)

    for csv_path in csv_files:
        window_id = csv_path.stem
        if window_id in processed_ids:
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
        windows.append(window)

    # Keep only the last MAX_WINDOWS windows
    windows.sort(key=lambda w: w.metrics.start_time)
    if len(windows) > MAX_WINDOWS:
        windows = windows[-MAX_WINDOWS:]

    save_windows(windows)
    print(f"[worker] Saved {len(windows)} windows to /var/netmon/windows.json", flush=True)

#    prune_files_by_windows(windows)


def main_loop() -> None:
    print("[worker] Starting combined PCAP->CSV and CSV->windows loop", flush=True)
    while True:
        try:
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

