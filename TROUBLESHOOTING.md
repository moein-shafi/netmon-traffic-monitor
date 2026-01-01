# Troubleshooting NetMon Services

## Check Service Logs

```bash
# Check API service logs
sudo journalctl -u netmon-api -n 50 --no-pager

# Check Worker service logs
sudo journalctl -u netmon-worker -n 50 --no-pager

# Follow logs in real-time
sudo journalctl -u netmon-api -f
sudo journalctl -u netmon-worker -f
```

## Common Issues

### 1. Service File Path Issues

Check if the paths in your service files are correct:

```bash
# Check API service file
sudo cat /etc/systemd/system/netmon-api.service

# Check Worker service file
sudo cat /etc/systemd/system/netmon-worker.service
```

**Common mistakes:**
- Wrong path to project directory
- Wrong path to virtual environment
- Wrong Python module path (should be `app.main:app` not `main:app`)

### 2. Fix Service Files

**API Service should be:**
```ini
[Unit]
Description=NetMon FastAPI API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/netmon
Environment="PATH=/opt/netmon/env/bin"
ExecStart=/opt/netmon/env/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Worker Service should be:**
```ini
[Unit]
Description=NetMon Worker Process
After=network.target netmon-api.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/netmon
Environment="PATH=/opt/netmon/env/bin"
ExecStart=/opt/netmon/env/bin/python -m app.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 3. Verify Paths Exist

```bash
# Check if paths exist
ls -la /opt/netmon
ls -la /opt/netmon/env/bin/python
ls -la /opt/netmon/env/bin/uvicorn
ls -la /opt/netmon/app/main.py
ls -la /opt/netmon/app/worker.py
```

### 4. Test Manually

```bash
# Activate virtual environment
cd /opt/netmon
source env/bin/activate

# Test API
uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal, test worker
cd /opt/netmon
source env/bin/activate
python -m app.worker
```

### 5. Check Python Path

```bash
# Check if Python can import the modules
cd /opt/netmon
source env/bin/activate
python -c "from app.main import app; print('OK')"
python -c "from app.worker import *; print('OK')"
```

### 6. Check Permissions

```bash
# Ensure directories are accessible
sudo chown -R root:root /opt/netmon
sudo chmod -R 755 /opt/netmon
```

### 7. Reload and Restart

```bash
# After fixing service files
sudo systemctl daemon-reload
sudo systemctl restart netmon-api
sudo systemctl restart netmon-worker
sudo systemctl status netmon-api
sudo systemctl status netmon-worker
```

