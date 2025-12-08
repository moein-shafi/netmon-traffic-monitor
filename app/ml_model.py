from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import joblib

# Where the trained model is stored
MODEL_PATH = Path("/opt/netmon/model/netmon_rf.joblib")

# Probability threshold for accepting the top class
ML_THRESHOLD = 0.90

# Features (columns in NTLFlowLyzer CSV) used by the model.
# Replace this list with the actual 20 features you select later.
FEATURE_COLUMNS = [
    "duration",
    "packets_count",
    "total_payload_bytes",
    "bytes_rate",
    "packets_rate",
    "active_mean",
    "idle_mean",
    "fwd_packets_IAT_mean",
    "bwd_packets_IAT_mean",
    "segment_size_mean",
    "subflow_fwd_packets",
    "subflow_bwd_packets",
    "subflow_fwd_bytes",
    "subflow_bwd_bytes",
    "handshake_duration",
    "packets_IAT_mean",
    "packets_IAT_std",
    "fwd_bytes_rate",
    "bwd_bytes_rate",
    "down_up_rate",
]

# How to treat different raw labels coming from the model
BENIGN_LABEL_CANONICAL = "Benign"


def _normalize_label(raw: str) -> str:
    s = raw.strip()
    if s.lower() in {"benign", "normal", "background"}:
        return BENIGN_LABEL_CANONICAL
    return s


_model = None
_model_loaded = False


def _load_model():
    """Lazy-load the model once."""
    global _model, _model_loaded
    if _model_loaded:
        return _model

    _model_loaded = True
    if not MODEL_PATH.exists():
        print(f"[ml_model] Model file not found at {MODEL_PATH}, ML disabled.")
        _model = None
        return None

    try:
        print(f"[ml_model] Loading model from {MODEL_PATH}")
        _model = joblib.load(MODEL_PATH)
    except Exception as e:
        print(f"[ml_model] Failed to load model: {e}")
        _model = None
    return _model


def model_is_ready() -> bool:
    """Return True if a model is loaded and ready."""
    return _load_model() is not None


def classify_row(row: Dict[str, str]) -> Optional[str]:
    """
    Classify a single CSV row (one flow).

    Returns:
      - 'Benign' (canonical benign label),
      - 'Unknown' (probability < ML_THRESHOLD),
      - <attack label string>,
      - or None if model not ready / row unusable.
    """
    model = _load_model()
    if model is None:
        return None

    try:
        x = []
        for col in FEATURE_COLUMNS:
            val = row.get(col)
            if val is None or val == "":
                x.append(0.0)
            else:
                x.append(float(val))
        # scikit-learn: predict_proba returns [n_samples, n_classes]
        probs = model.predict_proba([x])[0]
        # Pure Python argmax
        max_idx = max(range(len(probs)), key=lambda i: probs[i])
        max_prob = float(probs[max_idx])
        raw_label = str(model.classes_[max_idx])

        if max_prob < ML_THRESHOLD:
            return "Unknown"

        label = _normalize_label(raw_label)
        return label
    except Exception as e:
        # Treat classification errors as "Unknown but suspicious"
        print(f"[ml_model] classify_row error: {e}")
        return "Unknown"

