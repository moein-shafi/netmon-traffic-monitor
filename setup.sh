#!/bin/bash
# NetMon Traffic Monitor Setup Script

set -e

echo "🚀 NetMon Traffic Monitor Setup"
echo "================================"
echo ""

# Check Python version
echo "📋 Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   Found Python $python_version"
echo ""

# Create directories
echo "📁 Creating directories..."
sudo mkdir -p /var/pcaps
sudo mkdir -p /var/netmon/{flows,config,db}
sudo mkdir -p /opt/netmon/model
sudo chown -R $USER:$USER /var/netmon
echo "   ✓ Directories created"
echo ""

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt
echo "   ✓ Dependencies installed"
echo ""

# Initialize database
echo "🗄️  Initializing database..."
python3 -c "from app.database import init_db; init_db()"
echo "   ✓ Database initialized"
echo ""

# Create default admin user
echo "👤 Creating default admin user..."
echo "   Username: admin"
echo "   Password: admin"
echo "   ⚠️  IMPORTANT: Change this password immediately after first login!"
echo ""

# Copy systemd services
if [ -d "configs/systemd" ]; then
    echo "⚙️  Installing systemd services..."
    read -p "   Install systemd services? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sudo cp configs/systemd/*.service /etc/systemd/system/
        sudo systemctl daemon-reload
        echo "   ✓ Systemd services installed"
        echo "   To start services:"
        echo "     sudo systemctl start netmon-api"
        echo "     sudo systemctl start netmon-worker"
    fi
    echo ""
fi

echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Place your ML model at: /opt/netmon/model/netmon_rf.joblib"
echo "   2. Configure tcpdump to capture to /var/pcaps/"
echo "   3. Start the API: uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "   4. Start the worker: python3 -m app.worker_enhanced"
echo "   5. Access dashboard: http://localhost:8000/"
echo "   6. Access admin panel: http://localhost:8000/admin"
echo "   7. Change default admin password!"
echo ""

