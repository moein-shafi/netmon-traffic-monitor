from typing import List

from fastapi import FastAPI, HTTPException

from .storage import Window, load_windows

app = FastAPI(title="NetMon API", version="1.0.0")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/windows", response_model=List[Window])
def list_windows():
    windows = load_windows()
    windows.sort(key=lambda w: w.metrics.start_time, reverse=True)
    return windows


@app.get("/api/windows/latest", response_model=Window)
def latest_window():
    windows = load_windows()
    if not windows:
        raise HTTPException(status_code=404, detail="No windows yet")
    windows.sort(key=lambda w: w.metrics.start_time, reverse=True)
    return windows[0]
