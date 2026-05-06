#!/bin/bash

# Desktop Transcription Tool - Autostart Setup
# Installiert den Service für automatischen Start beim Systemstart

set -e

echo "╔═══════════════════════════════════════════════════════╗"
echo "║  🎤 Desktop Transcription Tool - Autostart Setup     ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_PATH="$SCRIPT_DIR"
OFFLINE_PATH="$PROJECT_PATH/offline"

echo "📁 Project Path: $PROJECT_PATH"
echo "📁 Offline Path: $OFFLINE_PATH"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# 1. Run installation if not done yet
if [ ! -d "$OFFLINE_PATH/.venv" ]; then
    echo -e "${BLUE}[1/4]${NC} Installing dependencies..."
    cd "$OFFLINE_PATH"
    ./install.sh
    cd "$PROJECT_DIR"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# 2. Create systemd user service directory
echo -e "${BLUE}[2/4]${NC} Setting up systemd service..."
mkdir -p ~/.config/systemd/user

# 3. Copy and customize service file
SERVICE_FILE=~/.config/systemd/user/transcription-offline.service
cp "$PROJECT_PATH/transcription-offline.service" "$SERVICE_FILE"

# Replace home directory placeholder with actual home
sed -i "s|%h|$HOME|g" "$SERVICE_FILE"
sed -i "s|%u|$USER|g" "$SERVICE_FILE"

echo -e "${GREEN}✓ Service file created: $SERVICE_FILE${NC}"

# 4. Reload systemd and enable service
echo -e "${BLUE}[3/4]${NC} Enabling autostart..."
systemctl --user daemon-reload
systemctl --user enable transcription-offline.service

echo -e "${GREEN}✓ Service enabled for autostart${NC}"

# 5. Optional: Start service now
echo ""
read -p "Start transcription service now? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}[4/4]${NC} Starting service..."
    systemctl --user start transcription-offline.service
    sleep 2
    systemctl --user status transcription-offline.service
    echo -e "${GREEN}✓ Service started!${NC}"
else
    echo -e "${YELLOW}⚠ Service will start on next login${NC}"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo -e "║  ${GREEN}✓ Autostart Setup Complete!${NC}                    ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "📋 Useful commands:"
echo "   Start service:    systemctl --user start transcription-offline"
echo "   Stop service:     systemctl --user stop transcription-offline"
echo "   View logs:        journalctl --user -u transcription-offline -f"
echo "   Disable autostart: systemctl --user disable transcription-offline"
echo ""
