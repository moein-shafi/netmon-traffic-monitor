#!/bin/bash
# NetMon Professional Deployment Script
# For moeinshafi.com integration

set -e

echo "🚀 NetMon Professional Deployment"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR=$(pwd)
VENV_DIR="${PROJECT_DIR}/venv"
SERVICE_USER="${USER}"
INSTALL_DIR="/opt/netmon"
DATA_DIR="/var/netmon"
PCAP_DIR="/var/pcaps"

echo -e "${BLUE}📋 Configuration:${NC}"
echo "  Project Directory: ${PROJECT_DIR}"
echo "  Virtual Environment: ${VENV_DIR}"
echo "  Install Directory: ${INSTALL_DIR}"
echo "  Data Directory: ${DATA_DIR}"
echo "  PCAP Directory: ${PCAP_DIR}"
echo ""

# Check Python
echo -e "${BLUE}🐍 Checking Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.9+"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "  ✓ Found ${PYTHON_VERSION}"
echo ""

# Create virtual environment
echo -e "${BLUE}📦 Setting up virtual environment...${NC}"
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
    echo "  ✓ Virtual environment created"
else
    echo "  ✓ Virtual environment exists"
fi

# Activate virtual environment
source "${VENV_DIR}/bin/activate"

# Upgrade pip
echo -e "${BLUE}⬆️  Upgrading pip...${NC}"
pip install --upgrade pip > /dev/null 2>&1
echo "  ✓ pip upgraded"
echo ""

# Install dependencies
echo -e "${BLUE}📥 Installing dependencies...${NC}"
pip install -r requirements.txt
echo "  ✓ Dependencies installed"
echo ""

# Create directories
echo -e "${BLUE}📁 Creating directories...${NC}"
sudo mkdir -p "${INSTALL_DIR}"/{model,env}
sudo mkdir -p "${DATA_DIR}"/{flows,config,db}
sudo mkdir -p "${PCAP_DIR}"
sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}"
sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" "${PCAP_DIR}"
echo "  ✓ Directories created"
echo ""

# Initialize database
echo -e "${BLUE}🗄️  Initializing database...${NC}"
python3 -c "from app.database import init_db; init_db()" 2>/dev/null || echo "  ⚠️  Database initialization (will be created on first run)"
echo "  ✓ Database ready"
echo ""

# Create systemd services
echo -e "${BLUE}⚙️  Setting up systemd services...${NC}"
if [ -d "configs/systemd" ]; then
    read -p "  Install systemd services? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Update service files with correct paths
        sed "s|/path/to/project|${PROJECT_DIR}|g" configs/systemd/netmon-api.service > /tmp/netmon-api.service
        sed "s|/path/to/project|${PROJECT_DIR}|g" configs/systemd/netmon-worker.service > /tmp/netmon-worker.service
        sed "s|/path/to/venv|${VENV_DIR}|g" /tmp/netmon-api.service > /tmp/netmon-api.service.new
        sed "s|/path/to/venv|${VENV_DIR}|g" /tmp/netmon-worker.service > /tmp/netmon-worker.service.new
        
        sudo cp /tmp/netmon-api.service.new /etc/systemd/system/netmon-api.service
        sudo cp /tmp/netmon-worker.service.new /etc/systemd/system/netmon-worker.service
        sudo systemctl daemon-reload
        echo "  ✓ Systemd services installed"
        echo ""
        echo "  To start services:"
        echo "    sudo systemctl start netmon-api"
        echo "    sudo systemctl start netmon-worker"
        echo "    sudo systemctl enable netmon-api"
        echo "    sudo systemctl enable netmon-worker"
    fi
fi
echo ""

# Set up Nginx (optional)
echo -e "${BLUE}🌐 Nginx configuration...${NC}"
if [ -d "configs/nginx" ]; then
    read -p "  Copy Nginx configuration? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ -f "configs/nginx/moeinshafi.conf" ]; then
            echo "  ⚠️  Please review and update configs/nginx/moeinshafi.conf"
            echo "  Then copy to /etc/nginx/sites-available/ and enable"
        fi
    fi
fi
echo ""

# Security setup
echo -e "${BLUE}🔐 Security setup...${NC}"
echo "  ⚠️  IMPORTANT: Change default admin password immediately!"
echo "  ⚠️  Review and update security settings in admin panel"
echo "  ⚠️  Configure API keys for LLM providers if needed"
echo ""

# Final instructions
echo -e "${GREEN}✅ Deployment complete!${NC}"
echo ""
echo -e "${YELLOW}📝 Next steps:${NC}"
echo "  1. Place your ML model at: ${INSTALL_DIR}/model/netmon_rf.joblib"
echo "  2. Configure tcpdump to capture to: ${PCAP_DIR}/"
echo "  3. Start the API:"
echo "     cd ${PROJECT_DIR}"
echo "     source ${VENV_DIR}/bin/activate"
echo "     uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "  4. Start the worker (in another terminal):"
echo "     cd ${PROJECT_DIR}"
echo "     source ${VENV_DIR}/bin/activate"
echo "     python -m app.worker"
echo "  5. Access dashboard: http://your-server:8000/"
echo "  6. Access admin: http://your-server:8000/admin"
echo "  7. Change default admin password!"
echo "  8. Configure LLM providers in admin panel"
echo ""
echo -e "${BLUE}🔗 Integration with moeinshafi.com:${NC}"
echo "  - Update Nginx config to proxy /netmon to this service"
echo "  - Or integrate directly into your main site"
echo "  - All pages are available:"
echo "    - / (main dashboard)"
echo "    - /admin (admin panel)"
echo "    - /analytics (advanced analytics)"
echo "    - /threat-intelligence (threat intel)"
echo "    - /model-performance (ML performance)"
echo ""
echo -e "${GREEN}🎉 Ready to showcase your expertise!${NC}"

