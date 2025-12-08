# NetMon Traffic Monitor

A small end-to-end setup for monitoring HTTP(S) traffic on a VPS:

- `tcpdump` rotates PCAP files every 5 minutes.
- [NTLFlowLyzer](https://github.com/ahlashkari/NTLFlowLyzer) extracts flows from PCAP.
- A scikit-learn model predicts attack vs benign flows.
- A local LLM (via Ollama) summarizes each 5-minute window.
- FastAPI exposes the last hour of windows at `/api/windows`.

## Project Layout

- `app/`
  - `main.py`    – FastAPI app, exposes `/api/health`, `/api/windows`, `/api/windows/latest`
  - `worker.py`  – background worker (PCAP -> CSV -> ML -> LLM)
  - `storage.py` – Pydantic models + JSON storage

- `configs/systemd/`
  - `pcap-capture.service`
  - `netmon-api.service`
  - `netmon-worker.service`

- `configs/nginx/`
  - `moeinshafi.conf` – Nginx site config

## Not Included

- The trained ML model (`/opt/netmon/model/model.joblib`)
- PCAPs (`/var/pcaps`) and flow CSVs (`/var/flows`)
- Local virtualenv (`env/`)

