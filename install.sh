#!/bin/bash

# Desktop Transcription Tool - Master Installation Script
# Installiert alle Tools und Abhängigkeiten

set -e

echo "╔════════════════════════════════════════════════════╗"
echo "║  🎤 Desktop Transcription Tool - Installation     ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. System dependencies
echo -e "${BLUE}[1/5]${NC} Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    xclip \
    xsel \
    xdotool \
    alsa-utils \
    pulseaudio-utils \
    portaudio19-dev \
    libsndfile1-dev > /dev/null 2>&1

echo -e "${GREEN}✓ System dependencies installed${NC}\n"

# 2. Create virtual environment (if not exists)
echo -e "${BLUE}[2/5]${NC} Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3.12 -m venv .venv > /dev/null 2>&1
    echo -e "${GREEN}✓ Virtual environment created${NC}\n"
else
    echo -e "${YELLOW}⚠ Virtual environment already exists${NC}\n"
fi

# 3. Install all requirements
echo -e "${BLUE}[3/5]${NC} Installing Python packages for all tools..."
source .venv/bin/activate

pip install --break-system-packages --upgrade pip setuptools wheel > /dev/null 2>&1

# Install offline requirements
echo "   → offline/ (Whisper)"
pip install --break-system-packages -q -r offline/requirements.txt

# Install online requirements
echo "   → online/ (Google API)"
pip install --break-system-packages -q -r online/requirements.txt

# Install big_audio_file requirements
if [ -f "big_audio_file_transcription/requirements.txt" ]; then
    echo "   → big_audio_file_transcription/ (Große Dateien)"
    pip install --break-system-packages -q -r big_audio_file_transcription/requirements.txt
fi

echo -e "${GREEN}✓ All packages installed${NC}\n"

# 4. Make scripts executable
echo -e "${BLUE}[4/5]${NC} Making scripts executable..."
chmod +x offline/transcription_offline.py
chmod +x offline/install.sh
chmod +x offline/run.sh
chmod +x online/transcription_online.py
chmod +x install.sh
echo -e "${GREEN}✓ Scripts are executable${NC}\n"

# 5. Create convenience scripts
echo -e "${BLUE}[5/5]${NC} Creating convenience commands..."

# Create run_offline.sh in root
cat > run_offline.sh << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
sudo "$(pwd)/.venv/bin/python" offline/transcription_offline.py
SCRIPT
chmod +x run_offline.sh

# Create run_online.sh in root
cat > run_online.sh << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate
python online/transcription_online.py
SCRIPT
chmod +x run_online.sh

echo -e "${GREEN}✓ Convenience scripts created${NC}\n"

# Summary
echo "╔════════════════════════════════════════════════════╗"
echo -e "║  ${GREEN}✓ Installation Complete!${NC}                      ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo -e "${BLUE}📋 Available Tools:${NC}"
echo ""
echo -e "${GREEN}1. OFFLINE Transcription${NC} (Whisper - lokal, kein API Key)"
echo "   Start: ${YELLOW}./run_offline.sh${NC}"
echo "   Oder:  ${YELLOW}cd offline && ./run.sh${NC}"
echo ""
echo -e "${GREEN}2. ONLINE Transcription${NC} (Google API - mit API Key)"
echo "   Start: ${YELLOW}./run_online.sh${NC}"
echo "   Oder:  ${YELLOW}cd online && python transcription_online.py${NC}"
echo ""
if [ -f "big_audio_file_transcription/transcribe_audio.py" ]; then
    echo -e "${GREEN}3. BIG AUDIO FILES${NC} (Große Audio-Dateien)"
    echo "   Start: ${YELLOW}cd big_audio_file_transcription && python transcribe_audio.py${NC}"
    echo ""
fi
echo -e "${BLUE}📚 Documentation:${NC}"
echo "   ${YELLOW}docs/README.md${NC}"
echo "   ${YELLOW}offline/README.md${NC}"
echo "   ${YELLOW}online/README.md${NC}"
echo ""
echo -e "${BLUE}🚀 Quick Start (Offline):${NC}"
echo "   ./run_offline.sh"
echo ""
echo "   Alt Tap Tap  → Start recording"
echo "   Speak 2-3 seconds"
echo "   Alt Tap Tap  → Stop & transcribe"
echo "   Ctrl+V       → Paste text"
echo ""
echo "═══════════════════════════════════════════════════════"
echo ""
