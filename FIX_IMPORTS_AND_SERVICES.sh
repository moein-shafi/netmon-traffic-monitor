#!/bin/bash
# Fix NetMon Service Files with PYTHONPATH

echo "Fixing NetMon service files with correct PYTHONPATH..."

# Fix API Service
sudo tee /etc/systemd/system/netmon-api.service > /dev/null << 'EOF'
[Unit]
Description=NetMon FastAPI API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/netmon
Environment="PATH=/opt/netmon/env/bin"
Environment="PYTHONPATH=/opt/netmon"
ExecStart=/opt/netmon/env/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Fix Worker Service
sudo tee /etc/systemd/system/netmon-worker.service > /dev/null << 'EOF'
[Unit]
Description=NetMon Worker Process
After=network.target netmon-api.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/netmon
Environment="PATH=/opt/netmon/env/bin"
Environment="PYTHONPATH=/opt/netmon"
ExecStart=/opt/netmon/env/bin/python -m app.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Service files updated. Reloading systemd..."
sudo systemctl daemon-reload

echo "Restarting services..."
sudo systemctl restart netmon-api
sudo systemctl restart netmon-worker

echo ""
echo "Checking status..."
sudo systemctl status netmon-api --no-pager -l | head -20
echo ""
sudo systemctl status netmon-worker --no-pager -l | head -20

echo ""
echo "If services are still failing, check logs:"
echo "  sudo journalctl -u netmon-api -n 30 --no-pager"
echo "  sudo journalctl -u netmon-worker -n 30 --no-pager"

