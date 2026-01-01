#!/bin/bash
# Fix NetMon Service Files

echo "Fixing NetMon service files..."

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
ExecStart=/opt/netmon/env/bin/python -m app.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "Service files updated. Now reloading systemd..."
sudo systemctl daemon-reload

echo "Restarting services..."
sudo systemctl restart netmon-api
sudo systemctl restart netmon-worker

echo ""
echo "Checking status..."
sudo systemctl status netmon-api --no-pager -l
echo ""
sudo systemctl status netmon-worker --no-pager -l

echo ""
echo "To view logs:"
echo "  sudo journalctl -u netmon-api -f"
echo "  sudo journalctl -u netmon-worker -f"

