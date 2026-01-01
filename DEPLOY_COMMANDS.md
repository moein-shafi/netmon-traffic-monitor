# NetMon Deployment Commands for 157.180.30.185

## Step 1: Connect to Your Server

```bash
ssh root@157.180.30.185
# Or if you have a different user:
# ssh your-username@157.180.30.185
```

## Step 2: Install System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and required tools
sudo apt install -y python3 python3-pip python3-venv git nginx

# Install tcpdump for packet capture (if not already installed)
sudo apt install -y tcpdump

# Install certbot for SSL (optional but recommended)
sudo apt install -y certbot python3-certbot-nginx
```

## Step 3: Clone/Upload Your Project

**Option A: If you have the project in Git:**
```bash
cd /opt
sudo git clone YOUR_REPO_URL netmon-traffic-monitor
cd netmon-traffic-monitor
```

**Option B: If you need to upload files:**
```bash
# Create directory
sudo mkdir -p /opt/netmon-traffic-monitor
cd /opt/netmon-traffic-monitor

# Upload your project files here using SCP from your local machine:
# scp -r /path/to/local/project/* root@157.180.30.185:/opt/netmon-traffic-monitor/
```

## Step 4: Set Up Python Environment

```bash
cd /opt/netmon-traffic-monitor

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install all dependencies
pip install -r requirements.txt
```

## Step 5: Create Required Directories

```bash
# Create data directories
sudo mkdir -p /var/netmon/{flows,config,db}
sudo mkdir -p /var/pcaps
sudo mkdir -p /opt/netmon/model

# Set ownership (replace 'root' with your username if different)
sudo chown -R $USER:$USER /var/netmon
sudo chown -R $USER:$USER /var/pcaps
sudo chown -R $USER:$USER /opt/netmon
```

## Step 6: Initialize Database

```bash
# Make sure you're in the project directory and venv is activated
cd /opt/netmon-traffic-monitor
source venv/bin/activate

# Initialize database
python -c "from app.database import init_db; init_db()"
```

## Step 7: Place ML Model (If You Have One)

```bash
# If you have a trained model, copy it here:
# sudo cp /path/to/your/model.joblib /opt/netmon/model/netmon_rf.joblib

# Or create a placeholder (worker will work without it, just won't do ML classification)
sudo touch /opt/netmon/model/netmon_rf.joblib
```

## Step 8: Test Run (Optional - to verify everything works)

```bash
# In one terminal, start the API
cd /opt/netmon-traffic-monitor
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# In another terminal (or screen/tmux), start the worker
cd /opt/netmon-traffic-monitor
source venv/bin/activate
python -m app.worker
```

**Test it:** Open `http://157.180.30.185:8000` in your browser

Press `Ctrl+C` to stop both when done testing.

## Step 9: Create Systemd Services (Production)

### Create API Service

```bash
sudo nano /etc/systemd/system/netmon-api.service
```

Paste this content (adjust paths if needed):

```ini
[Unit]
Description=NetMon API Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/netmon-traffic-monitor
Environment="PATH=/opt/netmon-traffic-monitor/venv/bin"
ExecStart=/opt/netmon-traffic-monitor/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save and exit (Ctrl+X, then Y, then Enter)

### Create Worker Service

```bash
sudo nano /etc/systemd/system/netmon-worker.service
```

Paste this content:

```ini
[Unit]
Description=NetMon Worker Process
After=network.target netmon-api.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/netmon-traffic-monitor
Environment="PATH=/opt/netmon-traffic-monitor/venv/bin"
ExecStart=/opt/netmon-traffic-monitor/venv/bin/python -m app.worker
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save and exit

### Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services (start on boot)
sudo systemctl enable netmon-api
sudo systemctl enable netmon-worker

# Start services
sudo systemctl start netmon-api
sudo systemctl start netmon-worker

# Check status
sudo systemctl status netmon-api
sudo systemctl status netmon-worker
```

## Step 10: Configure Nginx (Recommended)

### Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/netmon
```

Paste this configuration:

```nginx
server {
    listen 80;
    server_name 157.180.30.185;

    # Increase timeouts for long-running requests
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Save and exit

### Enable and Test Nginx

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/netmon /etc/nginx/sites-enabled/

# Remove default site (optional)
sudo rm /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# If test passes, reload nginx
sudo systemctl reload nginx
```

## Step 11: Configure Firewall (If Needed)

```bash
# Allow HTTP and HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp  # SSH

# If you want direct access to port 8000 (not recommended, use Nginx instead)
# sudo ufw allow 8000/tcp

# Enable firewall
sudo ufw enable
```

## Step 12: Set Up SSL (Optional but Recommended)

```bash
# Install SSL certificate (if you have a domain name)
# sudo certbot --nginx -d your-domain.com

# Or for IP-based access, you can skip SSL for now
```

## Step 13: Initial Configuration

1. **Access the Admin Panel:**
   - Open browser: `http://157.180.30.185/admin`
   - Login: `admin` / `admin`
   - **⚠️ IMMEDIATELY CHANGE THE PASSWORD!**

2. **Configure LLM Providers (Optional):**
   - Go to Admin → LLM Providers tab
   - Add API keys for paid providers if needed
   - Test connections
   - Save configuration

3. **Set Up Traffic Capture (Optional):**
   ```bash
   # Create a simple capture script
   sudo nano /usr/local/bin/netmon-capture.sh
   ```
   
   Paste:
   ```bash
   #!/bin/bash
   while true; do
     TIMESTAMP=$(date +%Y%m%d%H%M%S)
     tcpdump -i any -w /var/pcaps/window-${TIMESTAMP}.pcap -G 300 -W 1
   done
   ```
   
   ```bash
   sudo chmod +x /usr/local/bin/netmon-capture.sh
   
   # Run in background (optional)
   # nohup /usr/local/bin/netmon-capture.sh > /dev/null 2>&1 &
   ```

## Step 14: Verify Everything is Running

```bash
# Check API service
sudo systemctl status netmon-api

# Check Worker service
sudo systemctl status netmon-worker

# Check Nginx
sudo systemctl status nginx

# View API logs
sudo journalctl -u netmon-api -f

# View Worker logs
sudo journalctl -u netmon-worker -f
```

## Access Your Deployment

- **Main Dashboard**: `http://157.180.30.185/`
- **Admin Panel**: `http://157.180.30.185/admin`
- **Analytics**: `http://157.180.30.185/analytics`
- **Threat Intelligence**: `http://157.180.30.185/threat-intelligence`
- **ML Performance**: `http://157.180.30.185/model-performance`

## Troubleshooting

### If services won't start:

```bash
# Check logs
sudo journalctl -u netmon-api -n 50
sudo journalctl -u netmon-worker -n 50

# Check if port 8000 is in use
sudo netstat -tulpn | grep 8000

# Restart services
sudo systemctl restart netmon-api
sudo systemctl restart netmon-worker
```

### If you need to update code:

```bash
cd /opt/netmon-traffic-monitor
source venv/bin/activate
git pull  # if using git
# Or upload new files

# Restart services
sudo systemctl restart netmon-api
sudo systemctl restart netmon-worker
```

## Quick Reference Commands

```bash
# Start services
sudo systemctl start netmon-api netmon-worker

# Stop services
sudo systemctl stop netmon-api netmon-worker

# Restart services
sudo systemctl restart netmon-api netmon-worker

# View logs
sudo journalctl -u netmon-api -f
sudo journalctl -u netmon-worker -f

# Check status
sudo systemctl status netmon-api
sudo systemctl status netmon-worker
```

## Done! 🎉

Your NetMon is now running on `http://157.180.30.185`!

