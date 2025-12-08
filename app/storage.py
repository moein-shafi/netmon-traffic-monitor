from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


WINDOWS_PATH = Path("/var/netmon/windows.json")


@dataclass
class FeatureStats:
    mean: float
    min: float
    max: float


@dataclass
class WindowMetrics:
    start_time: datetime
    end_time: datetime
    total_flows: int
    total_packets: int
    benign_flows: int
    attack_flows: int
    attacks_per_label: Dict[str, int]
    total_payload_bytes: int
    feature_stats: Dict[str, FeatureStats]
    unknown_flows: int = 0  # NEW field for ML "Unknown / Need investigation" flows


@dataclass
class Window:
    id: str
    metrics: WindowMetrics
    llm_summary: str

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "metrics": {
                "start_time": self.metrics.start_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                "end_time": self.metrics.end_time.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                "total_flows": self.metrics.total_flows,
                "total_packets": self.metrics.total_packets,
                "benign_flows": self.metrics.benign_flows,
                "attack_flows": self.metrics.attack_flows,
                "unknown_flows": getattr(self.metrics, "unknown_flows", 0),
                "attacks_per_label": self.metrics.attacks_per_label,
                "total_payload_bytes": self.metrics.total_payload_bytes,
                "feature_stats": {
                    k: {"mean": v.mean, "min": v.min, "max": v.max}
                    for k, v in self.metrics.feature_stats.items()
                },
            },
            "llm_summary": self.llm_summary,
        }


def _metrics_from_dict(d: Dict) -> WindowMetrics:
    fs_dict = {
        name: FeatureStats(**stats)
        for name, stats in d.get("feature_stats", {}).items()
    }

    def parse_ts(s: str) -> datetime:
        # Handles ISO with 'Z'
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s)

    return WindowMetrics(
        start_time=parse_ts(d["start_time"]),
        end_time=parse_ts(d["end_time"]),
        total_flows=d.get("total_flows", 0),
        total_packets=d.get("total_packets", 0),
        benign_flows=d.get("benign_flows", 0),
        attack_flows=d.get("attack_flows", 0),
        attacks_per_label=d.get("attacks_per_label", {}),
        total_payload_bytes=d.get("total_payload_bytes", 0),
        feature_stats=fs_dict,
        unknown_flows=d.get("unknown_flows", 0),
    )


def load_windows() -> List[Window]:
    if not WINDOWS_PATH.exists():
        return []
    try:
        with WINDOWS_PATH.open("r") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"[storage] Failed to load windows.json: {e}")
        return []

    windows: List[Window] = []
    for item in raw:
        try:
            metrics = _metrics_from_dict(item["metrics"])
            windows.append(
                Window(
                    id=item["id"],
                    metrics=metrics,
                    llm_summary=item.get("llm_summary", ""),
                )
            )
        except Exception as e:
            print(f"[storage] Failed to parse window item: {e}")
            continue

    return windows


def save_windows(windows: List[Window]) -> None:
    WINDOWS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = [w.to_dict() for w in windows]
    with WINDOWS_PATH.open("w") as f:
        json.dump(data, f, indent=2)

