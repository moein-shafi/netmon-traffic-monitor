from __future__ import annotations

from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from storage import load_windows, Window

app = FastAPI(title="NetMon API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later if you want
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/windows")
def get_windows():
    windows: List[Window] = load_windows()
    return [w.to_dict() for w in windows]


@app.get("/api/windows/latest")
def get_latest_window():
    windows: List[Window] = load_windows()
    if not windows:
        raise HTTPException(status_code=404, detail="No windows available")

    latest = max(windows, key=lambda w: w.metrics.start_time)
    return latest.to_dict()

