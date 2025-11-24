#!/bin/bash
# Installation script for Road Photo Capture System
# Usage: sudo bash scripts/install.sh

set -e  # Exit on error

echo "============================================================"
echo "Road Photo Capture System - Installation Script"
echo "============================================================"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "Error: This script must be run as root (use sudo)"
   exit 1
fi

# Configuration
INSTALL_DIR="/opt/road-photo-capture"
SERVICE_USER="roadcapture"
SERVICE_GROUP="roadcapture"
LOG_DIR="/var/log/road-capture"
DATA_DIR="/var/lib/road-capture"

echo ""
echo "[1/8] Installing system dependencies..."
apt update
apt install -y \
    python3.9 \
    python3-pip \
    python3-venv \
    python3-dev \
    v4l-utils \
    libopencv-dev \
    build-essential

echo ""
echo "[2/8] Creating service user..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d $INSTALL_DIR $SERVICE_USER
    echo "✓ User $SERVICE_USER created"
else
    echo "✓ User $SERVICE_USER already exists"
fi

# Add user to required groups
usermod -a -G dialout $SERVICE_USER
usermod -a -G video $SERVICE_USER

echo ""
echo "[3/8] Creating directories..."
mkdir -p $INSTALL_DIR
mkdir -p $LOG_DIR
mkdir -p $DATA_DIR
mkdir -p /etc/road-photo-capture

echo ""
echo "[4/8] Copying application files..."
# Copy current directory to install location
cp -r . $INSTALL_DIR/
cd $INSTALL_DIR

echo ""
echo "[5/8] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "[6/8] Creating configuration..."
if [ ! -f /etc/road-photo-capture/config.yaml ]; then
    python src/config.py example /etc/road-photo-capture/config.yaml
    echo "✓ Example config created at /etc/road-photo-capture/config.yaml"
    echo "  IMPORTANT: Edit this file with your settings!"
else
    echo "✓ Config file already exists"
fi

if [ ! -f /etc/road-photo-capture/.env ]; then
    cp config/.env.example /etc/road-photo-capture/.env
    echo "✓ Example .env created at /etc/road-photo-capture/.env"
else
    echo "✓ .env file already exists"
fi

echo ""
echo "[7/8] Setting permissions..."
chown -R $SERVICE_USER:$SERVICE_GROUP $INSTALL_DIR
chown -R $SERVICE_USER:$SERVICE_GROUP $LOG_DIR
chown -R $SERVICE_USER:$SERVICE_GROUP $DATA_DIR
chown -R $SERVICE_USER:$SERVICE_GROUP /etc/road-photo-capture

echo ""
echo "[8/8] Installing systemd service..."
cp systemd/road-photo-capture.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable road-photo-capture

echo ""
echo "============================================================"
echo "Installation Complete!"
echo "============================================================"
echo ""
echo "Next steps:"
echo "  1. Edit configuration:"
echo "     nano /etc/road-photo-capture/config.yaml"
echo ""
echo "  2. Test hardware:"
echo "     cd $INSTALL_DIR"
echo "     source venv/bin/activate"
echo "     python scripts/test_hardware.py /dev/ttyUSB0"
echo ""
echo "  3. Test system:"
echo "     python main.py --test"
echo ""
echo "  4. Start service:"
echo "     sudo systemctl start road-photo-capture"
echo ""
echo "  5. Check status:"
echo "     sudo systemctl status road-photo-capture"
echo ""
echo "  6. View logs:"
echo "     sudo journalctl -u road-photo-capture -f"
echo ""
echo "Installation directory: $INSTALL_DIR"
echo "Config directory: /etc/road-photo-capture"
echo "Log directory: $LOG_DIR"
echo "============================================================"
