# NetMon Integration Guide for moeinshafi.com

## 🎯 Integration Overview

This guide helps you integrate NetMon with your personal website at [moeinshafi.com](https://moeinshafi.com/), showcasing your expertise in AI, Cybersecurity, and Software Engineering.

## 📋 Pre-Integration Checklist

- [ ] NetMon deployed and running
- [ ] SSL certificate configured
- [ ] Nginx installed and configured
- [ ] Domain DNS configured
- [ ] Firewall rules set up

## 🔗 Integration Options

### Option 1: Subdirectory Integration (`moeinshafi.com/netmon`)

**Pros:**
- Simple setup
- No subdomain needed
- Integrated with main site

**Steps:**

1. **Update Nginx Configuration**

Add to your main `moeinshafi.com` server block:

```nginx
location /netmon {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

2. **Update NetMon Base Path (if needed)**

If you want NetMon to work correctly with the `/netmon` prefix, you may need to configure FastAPI:

```python
# In app/main.py, add:
app = FastAPI(
    root_path="/netmon",  # Add this if using subdirectory
    ...
)
```

3. **Add Link to Your Website**

Add to your main website navigation:

```html
<a href="/netmon">NetMon - AI Security Platform</a>
```

### Option 2: Subdomain Integration (`netmon.moeinshafi.com`)

**Pros:**
- Clean separation
- Professional appearance
- Easier SSL management

**Steps:**

1. **Create DNS Record**

Add A record:
```
netmon.moeinshafi.com -> YOUR_SERVER_IP
```

2. **Configure Nginx**

Use the configuration from `configs/nginx/netmon-integration.conf`:

```bash
sudo cp configs/nginx/netmon-integration.conf /etc/nginx/sites-available/netmon.moeinshafi.com
sudo ln -s /etc/nginx/sites-available/netmon.moeinshafi.com /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

3. **SSL Certificate**

```bash
sudo certbot --nginx -d netmon.moeinshafi.com
```

4. **Add Link to Your Website**

```html
<a href="https://netmon.moeinshafi.com" target="_blank">NetMon - AI Security Platform</a>
```

## 🎨 Website Integration

### Adding to Your Portfolio

Update your `moeinshafi.com` projects section:

```html
<div class="project-card">
  <h3>NetMon - AI-Powered Network Security Platform</h3>
  <p>Enterprise-grade network traffic monitoring with ML-based threat detection and LLM-powered analysis.</p>
  <div class="tech-stack">
    <span>Python</span>
    <span>FastAPI</span>
    <span>Machine Learning</span>
    <span>Cybersecurity</span>
    <span>LLM Integration</span>
  </div>
  <a href="/netmon" class="btn">View Live Demo</a>
  <a href="https://github.com/yourusername/netmon" class="btn">View Code</a>
</div>
```

### Showcase Pages

NetMon includes several showcase pages perfect for your portfolio:

1. **Main Dashboard** (`/` or `/netmon`)
   - Real-time traffic monitoring
   - AI-powered insights
   - Professional visualizations

2. **Advanced Analytics** (`/analytics` or `/netmon/analytics`)
   - Deep traffic analysis
   - Trend visualization
   - Pattern recognition

3. **Threat Intelligence** (`/threat-intelligence` or `/netmon/threat-intelligence`)
   - Active threat monitoring
   - Attack pattern analysis
   - Security insights

4. **ML Model Performance** (`/model-performance` or `/netmon/model-performance`)
   - Model accuracy metrics
   - Classification performance
   - AI/ML showcase

5. **Admin Panel** (`/admin` or `/netmon/admin`)
   - System configuration
   - LLM provider management
   - Worker monitoring

## 🔐 Security Configuration

### 1. Change Default Credentials

**CRITICAL:** Immediately change the default admin password:

1. Access `/admin`
2. Login with `admin`/`admin`
3. Go to Users tab
4. Change your password

### 2. SSL/TLS Configuration

Ensure HTTPS is enabled:

```nginx
# Force HTTPS
server {
    listen 80;
    server_name netmon.moeinshafi.com;
    return 301 https://$server_name$request_uri;
}
```

### 3. Firewall Rules

```bash
# Allow only necessary ports
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (redirects to HTTPS)
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 4. API Key Security

- API keys are encrypted at rest
- Stored in `/var/netmon/config/.llm_secrets.json`
- File permissions: 600 (owner read/write only)
- Encryption key: `/var/netmon/config/.llm_encryption_key`

## 🚀 Deployment Steps

### 1. Run Deployment Script

```bash
chmod +x deploy.sh
./deploy.sh
```

### 2. Manual Setup (Alternative)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create directories
sudo mkdir -p /var/netmon/{flows,config,db}
sudo mkdir -p /var/pcaps
sudo mkdir -p /opt/netmon/model
sudo chown -R $USER:$USER /var/netmon

# Initialize database
python -c "from app.database import init_db; init_db()"

# Start services
uvicorn app.main:app --host 0.0.0.0 --port 8000
# In another terminal:
python -m app.worker
```

### 3. Systemd Services (Production)

```bash
# Edit service files with correct paths
sudo nano /etc/systemd/system/netmon-api.service
sudo nano /etc/systemd/system/netmon-worker.service

# Start services
sudo systemctl start netmon-api
sudo systemctl start netmon-worker
sudo systemctl enable netmon-api
sudo systemctl enable netmon-worker
```

## 📊 Showcase Features

### What to Highlight on Your Website

1. **AI/ML Integration**
   - Multiple LLM provider support
   - Machine learning threat detection
   - Intelligent traffic analysis

2. **Cybersecurity Expertise**
   - Real-time threat monitoring
   - Network traffic analysis
   - Security operations dashboard

3. **Software Engineering**
   - Production-ready architecture
   - Comprehensive monitoring
   - Enterprise-grade features

4. **Full-Stack Development**
   - Modern backend (FastAPI)
   - Professional frontend
   - Real-time updates

## 🎯 Resume Integration

### Add to Your Projects Section

**Project:** NetMon - AI-Powered Network Security Platform

**Description:**
Enterprise-grade network traffic monitoring system with ML-based threat detection, LLM-powered analysis, and comprehensive security operations dashboard. Features multi-LLM provider support, real-time threat intelligence, advanced analytics, and production-ready architecture.

**Technologies:**
- Python, FastAPI, SQLAlchemy
- Machine Learning (Scikit-learn)
- LLM Integration (OpenAI, Anthropic, Ollama, etc.)
- Network Traffic Analysis
- Real-time Monitoring & Alerting

**Key Features:**
- Multi-LLM provider support with secure API key management
- ML-based threat classification
- Real-time traffic analysis
- Advanced analytics and visualization
- Enterprise-grade monitoring and metrics
- Comprehensive admin panel

**Live Demo:** [netmon.moeinshafi.com](https://netmon.moeinshafi.com)

## 🔧 Configuration

### LLM Provider Setup

1. **Free Providers (No API Key)**
   - Ollama (Local)
   - Hugging Face (Free tier)

2. **Paid Providers (Require API Key)**
   - OpenAI GPT-4
   - Anthropic Claude
   - Google Gemini
   - Cohere
   - Mistral AI
   - Groq
   - Together AI

**To Configure:**
1. Go to Admin Panel → LLM Providers
2. Select provider
3. Enter API key (for paid providers)
4. Select model
5. Test connection
6. Save configuration

### Worker Configuration

Configure in Admin Panel → Worker Status:
- Processing intervals
- Retry logic
- Parallel processing
- Performance tuning

## 📈 Monitoring

### Health Checks

- API Health: `GET /api/health`
- Worker Health: `GET /api/worker/health`
- System Status: `GET /api/system/status`

### Metrics

Access detailed metrics in Admin Panel → Worker Status:
- Processing statistics
- Performance metrics
- Error tracking
- Activity monitoring

## 🎓 Perfect For Showcasing

This integration demonstrates:

1. **Production Deployment**
   - Real-world deployment
   - Professional setup
   - Security best practices

2. **Full-Stack Skills**
   - Backend API development
   - Frontend UI/UX
   - System integration

3. **AI/ML Expertise**
   - Multiple LLM integration
   - ML model deployment
   - Intelligent analysis

4. **Cybersecurity**
   - Network monitoring
   - Threat detection
   - Security operations

## 🔗 Links to Add to Your Website

```html
<!-- Projects Section -->
<a href="https://netmon.moeinshafi.com">NetMon - Live Demo</a>
<a href="https://netmon.moeinshafi.com/analytics">Advanced Analytics</a>
<a href="https://netmon.moeinshafi.com/threat-intelligence">Threat Intelligence</a>
<a href="https://netmon.moeinshafi.com/model-performance">ML Performance</a>
```

## 📝 Maintenance

### Regular Tasks

1. **Monitor Worker Status**
   - Check Admin Panel → Worker Status
   - Review error logs
   - Monitor performance metrics

2. **Update Dependencies**
   ```bash
   source venv/bin/activate
   pip install --upgrade -r requirements.txt
   ```

3. **Backup Database**
   ```bash
   cp /var/netmon/db/netmon.db /backup/netmon-$(date +%Y%m%d).db
   ```

4. **Review Logs**
   ```bash
   journalctl -u netmon-api -f
   journalctl -u netmon-worker -f
   ```

## 🎉 Result

You now have a **world-class, production-ready** network monitoring system integrated with your personal website, perfectly showcasing your expertise in:

- ✅ AI/ML Engineering
- ✅ Cybersecurity
- ✅ Software Engineering
- ✅ Full-Stack Development
- ✅ DevOps & Deployment

**Perfect for your resume and portfolio!** 🚀💼

