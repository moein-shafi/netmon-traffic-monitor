from __future__ import annotations

import json
import logging
import subprocess
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

import joblib
import pandas as pd
import requests

from .storage import Window, WindowMetrics, load_windows, save_windows

PCAP_DIR = Path("/var/pcaps")
FLOW_DIR = Path("/var/flows")
MODEL_PATH = Path("/opt/netmon/model/model.joblib")  # <-- put your model here
LLM_URL = "http://127.0.0.1:11434/api/generate"
LLM_MODEL_NAME = "smollm2:135m"  # or any model you've pulled in Ollama
CHECK_INTERVAL_SECONDS = 60
WINDOW_MINUTES = 5

logger = logging.getLogger("netmon-worker")


def load_model():
    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"ML model not found at {MODEL_PATH}. "
            f"Place your trained model there or update MODEL_PATH."
        )
    model = joblib.load(MODEL_PATH)
    logger.info("Loaded ML model from %s", MODEL_PATH)
    return model


MODEL = None  # will be set in main()


def parse_window_times(pcap_path: Path):
    """
    Expect filenames like: window-YYYYmmddHHMMSS.pcap
    """
    stem = pcap_path.stem  # e.g., "window-20251207153000"
    try:
        ts_str = stem.split("window-")[-1]
        start = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
    except Exception:
        logger.warning("Could not parse time from %s, skipping", pcap_path.name)
        return None, None
    end = start + timedelta(minutes=WINDOW_MINUTES)
    return start, end


def build_ntl_config(pcap_path: Path, csv_path: Path, config_path: Path):
    config = {
        "pcap_file_address": str(pcap_path),
        "output_file_address": str(csv_path),
        "label": "Unknown",
        "number_of_threads": 4,
    }
    with config_path.open("w") as f:
        json.dump(config, f, indent=2)
    return config_path


def run_ntlflowlyzer(pcap_path: Path, csv_path: Path):
    """
    Runs NTLFlowLyzer via its CLI using a tiny config file.
    """
    config_path = FLOW_DIR / f"{pcap_path.stem}.json"
    build_ntl_config(pcap_path, csv_path, config_path)
    logger.info("Running NTLFlowLyzer on %s", pcap_path.name)
    subprocess.run(
        ["ntlflowlyzer", "-c", str(config_path)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    logger.info("NTLFlowLyzer finished for %s", pcap_path.name)


def run_ml(csv_path: Path):
    """
    Load flow CSV, run ML model, and compute basic stats.
    """
    df = pd.read_csv(csv_path)
    if df.empty:
        logger.warning("Flow CSV %s is empty", csv_path)
        return 0, 0, 0, 0, {}

    total_packets = 0
    if "PacketsCount" in df.columns:
        total_packets = int(df["PacketsCount"].sum())

    # Drop label column if NTLFlowLyzer added it; keep everything else
    drop_cols = [c for c in ["label"] if c in df.columns]
    X = df.drop(columns=drop_cols) if drop_cols else df

    preds = MODEL.predict(X)
    label_counts = Counter(map(str, preds))
    total_flows = len(preds)

    # Heuristic: treat these labels as benign; everything else = attack
    benign_names = {"BENIGN", "Benign", "NORMAL", "Normal", "0"}
    benign_flows = sum(count for label, count in label_counts.items() if label in benign_names)
    attack_flows = total_flows - benign_flows

    return total_flows, total_packets, benign_flows, attack_flows, dict(label_counts)


def generate_llm_summary(metrics: WindowMetrics, attacks_per_label: Dict[str, int]) -> str:
    """
    Call local LLM (Ollama) to summarize this 5-minute window.
    """
    prompt = f"""
You are a cybersecurity assistant. Summarize the last 5 minutes of network activity for a technical user.

Time window:
- Start (UTC): {metrics.start_time.isoformat()}
- End   (UTC): {metrics.end_time.isoformat()}

Metrics:
- Total flows: {metrics.total_flows}
- Total packets: {metrics.total_packets}
- Benign flows: {metrics.benign_flows}
- Attack flows: {metrics.attack_flows}
- Flows per predicted label: {json.dumps(attacks_per_label, indent=2)}

In 3–5 bullet points, describe:
1. What kind of traffic pattern you see
2. Whether there are signs of possible attacks
3. Any notable spikes or anomalies
4. A short overall risk rating (low / medium / high)

Keep it concise and objective.
""".strip()

    try:
        resp = requests.post(
            LLM_URL,
            json={
                "model": LLM_MODEL_NAME,
                "prompt": prompt,
                "stream": False,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        if not text:
            return "LLM summary unavailable (empty response)."
        return text
    except Exception as e:
        logger.exception("Error calling LLM")
        return f"LLM summary unavailable (error: {e})"


def process_once():
    """
    Scan /var/pcaps for new finished PCAP files and process them.
    """
    windows = load_windows()
    known_ids = {w.id for w in windows}

    now = datetime.utcnow()

    for pcap_path in sorted(PCAP_DIR.glob("window-*.pcap")):
        window_id = pcap_path.stem

        if window_id in known_ids:
            continue  # already processed

        # Avoid processing files that are still being written
        mtime = datetime.utcfromtimestamp(pcap_path.stat().st_mtime)
        if (now - mtime) < timedelta(seconds=60):
            continue

        start_time, end_time = parse_window_times(pcap_path)
        if start_time is None:
            continue

        csv_path = FLOW_DIR / f"{pcap_path.stem}.csv"

        try:
            run_ntlflowlyzer(pcap_path, csv_path)
            total_flows, total_packets, benign_flows, attack_flows, attacks_per_label = run_ml(csv_path)

            metrics = WindowMetrics(
                start_time=start_time,
                end_time=end_time,
                total_flows=total_flows,
                total_packets=total_packets,
                benign_flows=benign_flows,
                attack_flows=attack_flows,
                attacks_per_label=attacks_per_label,
            )

            summary = generate_llm_summary(metrics, attacks_per_label)

            new_window = Window(
                id=window_id,
                metrics=metrics,
                llm_summary=summary,
            )
            windows.append(new_window)

            # Keep only last 12 windows (1 hour)
            windows.sort(key=lambda w: w.metrics.start_time)
            windows = windows[-12:]
            save_windows(windows)

            logger.info(
                "Processed window %s: flows=%d, packets=%d, attacks=%d",
                window_id,
                total_flows,
                total_packets,
                attack_flows,
            )
        except Exception:
            logger.exception("Error processing %s", pcap_path)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    global MODEL
    MODEL = load_model()

    logger.info("Starting NetMon worker loop")
    while True:
        process_once()
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
