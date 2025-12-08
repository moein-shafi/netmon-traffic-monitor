from __future__ import annotations

from pydantic import BaseModel
from typing import Dict, List
from datetime import datetime
from pathlib import Path
import json
import threading

WINDOWS_FILE = Path("/opt/netmon/data/windows.json")
_LOCK = threading.Lock()


class WindowMetrics(BaseModel):
    start_time: datetime
    end_time: datetime
    total_flows: int
    total_packets: int
    benign_flows: int
    attack_flows: int
    attacks_per_label: Dict[str, int]


class Window(BaseModel):
    id: str
    metrics: WindowMetrics
    llm_summary: str


def _model_to_dict(m: BaseModel) -> dict:
    # Works for both Pydantic v1 and v2
    if hasattr(m, "model_dump_json"):
        return json.loads(m.model_dump_json())
    return json.loads(m.json())


def load_windows() -> List[Window]:
    if not WINDOWS_FILE.exists():
        return []
    with _LOCK:
        with WINDOWS_FILE.open() as f:
            raw = json.load(f)
    return [Window(**w) for w in raw]


def save_windows(windows: List[Window]) -> None:
    data = [_model_to_dict(w) for w in windows]
    WINDOWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with WINDOWS_FILE.open("w") as f:
            json.dump(data, f, indent=2)
