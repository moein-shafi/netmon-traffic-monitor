# NetMon Traffic Monitor - Professional Edition

A comprehensive, production-ready network traffic monitoring system with ML-based threat detection, LLM-powered analysis, and a beautiful, configurable dashboard. Perfect for showcasing skills in AI, Cybersecurity, and Software Engineering.

## 🌟 Features

### Core Capabilities
- **Real-time Traffic Monitoring**: Captures and analyzes network traffic in 5-minute windows
- **ML-Based Threat Detection**: Uses scikit-learn models to classify flows as benign, attack, or unknown
- **Multi-LLM Support**: Supports 9+ LLM providers (OpenAI, Anthropic, Google, Ollama, and more) with secure API key management
- **Professional Dashboard**: Beautiful, responsive UI with real-time visualizations
- **Comprehensive Analytics**: Detailed metrics, charts, and insights
- **Multiple Showcase Pages**: Analytics, Threat Intelligence, ML Performance pages

### Enterprise Features
- **Authentication & Authorization**: JWT-based auth with admin/user roles
- **Configuration Management**: Public and admin-only settings, fully configurable
- **Alert System**: Automated alerts for suspicious activity with severity levels
- **Audit Logging**: Complete audit trail of all system actions
- **Data Export**: Export data in CSV and JSON formats
- **Database Backend**: SQLite with SQLAlchemy for robust data management
- **Admin Panel**: Full-featured admin interface for system management

### Technical Highlights
- **FastAPI Backend**: Modern, async Python web framework
- **SQLAlchemy ORM**: Professional database abstraction
- **JWT Authentication**: Secure token-based authentication
- **RESTful API**: Well-structured API endpoints
- **Responsive UI**: Mobile-friendly dashboard design
- **Real-time Updates**: Auto-refreshing dashboard with configurable intervals

## 📋 Requirements

- Python 3.9+
- tcpdump (for PCAP capture)
- NTLFlowLyzer (for flow extraction)
- Ollama (for LLM summaries, optional)
- Trained ML model (scikit-learn joblib format)

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd netmon-traffic-monitor
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up Directories

```bash
sudo mkdir -p /var/pcaps
sudo mkdir -p /var/netmon/{flows,config,db}
sudo mkdir -p /opt/netmon/model
sudo chown -R $USER:$USER /var/netmon
```

### 4. Configure System Services

Copy systemd service files from `configs/systemd/` to `/etc/systemd/system/`:

```bash
sudo cp configs/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 5. Place ML Model

Place your trained model at:
```
/opt/netmon/model/netmon_rf.joblib
```

### 6. Configure PCAP Capture

Set up tcpdump to rotate PCAP files every 5 minutes. Example script:

```bash
#!/bin/bash
while true; do
  TIMESTAMP=$(date +%Y%m%d%H%M%S)
  tcpdump -i any -w /var/pcaps/window-${TIMESTAMP}.pcap -G 300 -W 1
done
```

## 🔧 Configuration

### Public Configuration

Public settings (accessible to all authenticated users):
- Dashboard refresh interval
- Display preferences
- Alert thresholds
- Theme settings

Access via: `/api/config/public`

### Admin Configuration

Admin-only settings (requires admin role):
- Capture directories
- ML model settings
- LLM/Ollama configuration
- NTLFlowLyzer settings
- Security settings
- Storage configuration
- Notification settings

Access via: `/api/admin/config` (admin only)

### Initial Setup

1. **Default Admin User**: 
   - Username: `admin`
   - Password: `admin` (⚠️ **CHANGE THIS IMMEDIATELY**)

2. **Access Admin Panel**: Navigate to `/admin` and log in

3. **Change Default Password**: Use the admin panel to update your password

4. **Configure System**: Adjust settings in the admin panel as needed

## 📖 API Documentation

### Public Endpoints

- `GET /` - Main dashboard
- `GET /api/health` - Health check
- `GET /api/windows` - Get all traffic windows
- `GET /api/windows/latest` - Get latest window
- `GET /api/config/public` - Get public configuration
- `PUT /api/config/public` - Update public configuration (authenticated)
- `GET /api/alerts` - Get alerts
- `GET /api/analytics/summary` - Get analytics summary
- `POST /api/auth/login` - Authenticate user

### Admin Endpoints

- `GET /admin` - Admin panel
- `GET /api/admin/config` - Get admin configuration
- `PUT /api/admin/config` - Update admin configuration
- `GET /api/admin/users` - List users
- `POST /api/admin/users` - Create user
- `PUT /api/admin/users/{username}/password` - Update user password
- `GET /api/admin/audit-logs` - Get audit logs
- `POST /api/admin/alerts/{id}/acknowledge` - Acknowledge alert
- `POST /api/admin/alerts/{id}/resolve` - Resolve alert
- `GET /api/admin/export/csv` - Export data as CSV
- `GET /api/admin/export/json` - Export data as JSON

## 🎯 Usage

### Starting the Services

1. **Start the API server**:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

2. **Start the worker** (in a separate terminal):
```bash
python -m app.worker_enhanced
```

Or use systemd services:
```bash
sudo systemctl start netmon-api
sudo systemctl start netmon-worker
```

### Accessing the Dashboard

- **Main Dashboard**: http://localhost:8000/
- **Advanced Analytics**: http://localhost:8000/analytics
- **Threat Intelligence**: http://localhost:8000/threat-intelligence
- **ML Model Performance**: http://localhost:8000/model-performance
- **Admin Panel**: http://localhost:8000/admin

### Monitoring Traffic

1. Ensure tcpdump is capturing traffic to `/var/pcaps/`
2. The worker will automatically:
   - Convert PCAP files to CSV using NTLFlowLyzer
   - Run ML classification on flows
   - Generate LLM summaries
   - Create alerts for suspicious activity
   - Store everything in the database

## 🏗️ Architecture

```
┌─────────────┐
│   tcpdump   │ → PCAP files
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Worker    │ → CSV → ML → LLM → Database
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Database   │ (SQLite)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  FastAPI    │ → Dashboard & API
└─────────────┘
```

## 🔐 Security Considerations

1. **Change Default Credentials**: Immediately change the default admin password
2. **Use HTTPS**: Configure reverse proxy (nginx) with SSL/TLS
3. **Restrict Access**: Use firewall rules to limit access
4. **Regular Updates**: Keep dependencies updated
5. **Secure Storage**: Protect configuration files and database
6. **Audit Logs**: Regularly review audit logs for suspicious activity

## 📊 Dashboard Features

### Main Dashboard
- Real-time traffic metrics
- Interactive charts and visualizations
- Latest window analysis
- Attack type distribution
- AI analyst console with LLM summaries
- Executive signals and risk indicators
- Complete windows table

### Admin Panel
- Configuration management (public & admin)
- **LLM Provider Management**: Configure and test multiple LLM providers with secure API key storage
- Worker status and configuration
- User management
- Alert management
- Audit log viewer
- Data export tools

## 🧪 Development

### Project Structure

```
netmon-traffic-monitor/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── worker.py            # Original worker
│   ├── worker_enhanced.py   # Enhanced worker with config
│   ├── storage.py           # Data models
│   ├── ml_model.py          # ML classification
│   ├── auth.py              # Authentication system
│   ├── config.py            # Configuration management
│   ├── database.py          # Database models
│   └── alerts.py            # Alert system
├── templates/
│   ├── index.html           # Main dashboard
│   └── admin.html           # Admin panel
├── configs/
│   └── systemd/             # Systemd service files
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

### Running in Development

```bash
# Terminal 1: API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Worker
python -m app.worker_enhanced
```

## 🎓 Skills Demonstrated

This project showcases expertise in:

- **AI/ML**: Scikit-learn models, feature engineering, classification
- **Cybersecurity**: Network monitoring, threat detection, security analysis
- **Software Engineering**: Clean architecture, RESTful APIs, database design
- **Full-Stack Development**: FastAPI backend, modern frontend, real-time updates
- **DevOps**: Systemd services, configuration management, deployment
- **UI/UX Design**: Professional, responsive, beautiful interfaces

## 📝 License

[Specify your license here]

## 👤 Author

**Arash** - Professional Network Security Engineer

## 🙏 Acknowledgments

- NTLFlowLyzer for flow extraction
- Ollama for local LLM capabilities
- FastAPI for the excellent web framework
- All open-source contributors

## 📧 Contact

For questions or contributions, please open an issue or contact the maintainer.

---

**Note**: This is a professional-grade monitoring system. Ensure proper security measures are in place before deploying to production.
