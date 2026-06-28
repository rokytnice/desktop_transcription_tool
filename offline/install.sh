#!/bin/bash

# Transcription Tool Installation Script
# Installiert alle Abhängigkeiten und richtet das System auf

set -e  # Exit on error

echo "================================================"
echo "🎤 Transcription Tool - Installation"
echo "================================================"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. System dependencies
echo -e "${BLUE}[1/4]${NC} Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    wl-clipboard \
    alsa-utils \
    pulseaudio-utils \
    portaudio19-dev \
    libsndfile1-dev

echo -e "${GREEN}✓ System dependencies installed${NC}\n"

# 2. Create virtual environment
echo -e "${BLUE}[2/4]${NC} Creating Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3.12 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}\n"
else
    echo -e "${YELLOW}⚠ Virtual environment already exists${NC}\n"
fi

# 3. Install Python packages
echo -e "${BLUE}[3/4]${NC} Installing Python packages..."
source .venv/bin/activate
pip install --break-system-packages --upgrade pip setuptools wheel
pip install --break-system-packages -r requirements.txt
echo -e "${GREEN}✓ Python packages installed${NC}\n"

# 4. Make scripts executable
echo -e "${BLUE}[4/4]${NC} Making scripts executable..."
chmod +x transcription_offline.py
chmod +x install.sh
echo -e "${GREEN}✓ Scripts are executable${NC}\n"

# Summary
echo "================================================"
echo -e "${GREEN}✓ Installation complete!${NC}"
echo "================================================"
echo ""
echo "🚀 To start the transcription tool:"
echo ""
echo "   source .venv/bin/activate"
echo "   sudo python transcription_offline.py"
echo ""
echo "📝 Usage:"
echo "   - Alt Tap Tap → Start recording"
echo "   - Speak 2-3 seconds"
echo "   - Alt Tap Tap → Stop & transcribe"
echo "   - Ctrl+V → Paste the text"
echo ""
echo "📋 Text automatically copied to clipboard!"
echo "================================================"
